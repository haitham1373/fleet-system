"""مزامنة حالة التطبيق مع GitHub على الاستضافات ذات القرص المؤقت.

الفكرة: ``fleet.db`` الموجود على الفرع الرئيسي يفضل هو الأساس ولا يتلمس.
البيانات الحية (قاعدة البيانات والمرفوعات) بتتخزن في فرع منفصل
(``fleet-state`` افتراضياً) تحت مجلد ``cloud_state/``. كده الـ push مش بيعمل
Redeploy للتطبيق، والبيانات بترجع بعد كل Reboot.

المزامنة متعطّلة تماماً لو مفيش ``GITHUB_TOKEN`` في أسرار Streamlit أو
متغيرات البيئة — يعني التشغيل المحلي زي ما هو بالظبط.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

_BASE_DIR = Path(__file__).resolve().parent.parent
_LOCAL_STATE_DIR = _BASE_DIR / ".fleet_state"
_LOCAL_DB = _LOCAL_STATE_DIR / "fleet.db"

_DB_KEY = "cloud_state/fleet.db"
_UPLOADS_PREFIX = "cloud_state/uploads"
_MANIFEST_KEY = f"{_UPLOADS_PREFIX}/manifest.json"

_last_db_hash: str | None = None
_prepared = False
_STATE_ERROR: str | None = None
_pending_push = False
_pending_uploads: set[str] = set()
_last_retry = 0.0


# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------
def _settings() -> tuple[str, str, str, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "haitham1373/fleet-system")
    state_branch = os.environ.get("GITHUB_STATE_BRANCH", "fleet-state")
    source_branch = os.environ.get("GITHUB_SOURCE_BRANCH", "main")

    try:  # أسرار Streamlit أولاً لو موجودة
        import streamlit as st

        secrets = st.secrets
        token = secrets.get("GITHUB_TOKEN", token) or token
        repo = secrets.get("GITHUB_REPO", repo) or repo
        state_branch = secrets.get("GITHUB_STATE_BRANCH", state_branch) or state_branch
        source_branch = secrets.get("GITHUB_SOURCE_BRANCH", source_branch) or source_branch
    except Exception:
        pass

    return (
        str(token).strip(),
        str(repo).strip(),
        str(state_branch).strip(),
        str(source_branch).strip(),
    )


def enabled() -> bool:
    """هل المزامنة مفعّلة؟"""
    return bool(_settings()[0])


def get_error() -> str | None:
    """آخر خطأ مزامنة، لو حصل."""
    return _STATE_ERROR


# ---------------------------------------------------------------------------
# GitHub Contents API
# ---------------------------------------------------------------------------
def _api(method: str, path: str, payload: dict | None = None) -> dict:
    token, repo, _, _ = _settings()
    url = f"https://api.github.com/repos/{repo}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fleet-system-state-sync",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def get_file(key: str) -> tuple[bytes | None, str | None]:
    """يرجع (المحتوى، SHA) أو (None, None) لو الملف مش موجود."""
    if not enabled():
        return None, None
    _, _, branch, _ = _settings()
    path = f"contents/{quote(key, safe='/')}?ref={quote(branch, safe='')}"
    try:
        payload = _api("GET", path)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        raise

    sha = payload.get("sha")
    content = payload.get("content")
    if content and payload.get("encoding") == "base64":
        return base64.b64decode(content), sha

    download_url = payload.get("download_url")
    if download_url:
        token = _settings()[0]
        request = urllib.request.Request(
            download_url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "fleet-system-state-sync",
            },
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.read(), sha
    return b"", sha


def put_file(key: str, data: bytes, message: str, sha: str | None = None) -> dict:
    """ينشئ أو يحدّث ملفاً في فرع الحالة، مع إعادة محاولة عند التعارض."""
    _, _, branch, _ = _settings()
    path = f"contents/{quote(key, safe='/')}"
    for attempt in range(4):
        payload: dict = {
            "message": message,
            "content": base64.b64encode(data).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        try:
            return _api("PUT", path, payload)
        except urllib.error.HTTPError as error:
            if error.code == 409 and attempt < 3:
                _, sha = get_file(key)
                continue
            raise
    raise RuntimeError("تعذر حفظ الملف بعد عدة محاولات.")


def ensure_branch() -> None:
    """ينشئ فرع الحالة من الفرع الرئيسي لو مش موجود."""
    _, _, state_branch, source_branch = _settings()
    try:
        _api("GET", f"git/ref/heads/{quote(state_branch, safe='')}")
        return
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise

    source = _api("GET", f"git/ref/heads/{quote(source_branch, safe='')}")
    sha = source["object"]["sha"]
    try:
        _api(
            "POST",
            "git/refs",
            {"ref": f"refs/heads/{state_branch}", "sha": sha},
        )
    except urllib.error.HTTPError as error:
        if error.code != 422:  # 422 يعني الفرع اتعمل بالفعل
            raise


# ---------------------------------------------------------------------------
# التحميل والحفظ
# ---------------------------------------------------------------------------
def _restore_uploads() -> None:
    manifest, _ = get_file(_MANIFEST_KEY)
    if not manifest:
        return
    try:
        files = json.loads(manifest).get("files", [])
    except (ValueError, TypeError):
        return

    for relative_path in files:
        local = (_BASE_DIR / str(relative_path)).resolve()
        if not local.is_relative_to(_BASE_DIR) or local.exists():
            continue
        data, _ = get_file(f"{_UPLOADS_PREFIX}/{relative_path}")
        if data:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)


def _backup_local_db() -> None:
    """نسخة احتياطية محلية قبل أي استبدال للملف (آخر 5 نسخ)."""
    if not _LOCAL_DB.exists():
        return
    backup_dir = _LOCAL_STATE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(_LOCAL_DB, backup_dir / f"fleet_{stamp}.db")
    for old in sorted(backup_dir.glob("fleet_*.db"))[:-5]:
        old.unlink()


def prepare_state() -> None:
    """يجهّز نسخة محلية من الحالة قبل قراءة ``DB_PATH`` في config."""
    global _prepared
    if _prepared:
        return
    _prepared = True

    user_path = os.environ.get("FLEET_DB_PATH")
    if user_path and Path(user_path).resolve() != _LOCAL_DB.resolve():
        return  # المستخدم حدد مسار صريح — ما نغيرهاش.
    if not enabled():
        return

    _LOCAL_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if _LOCAL_DB.exists():
        _backup_local_db()

    try:
        ensure_branch()
        local_data = _LOCAL_DB.read_bytes() if _LOCAL_DB.exists() else None
        remote_data, _ = get_file(_DB_KEY)

        if local_data is not None and remote_data is not None and local_data != remote_data:
            # النسخة المحلية فيها تغييرات لسه مترفعتش — ما نستبدلها أبداً بالبعيدة.
            push_db()
        elif local_data is None:
            if remote_data is None:
                seed = _BASE_DIR / "fleet.db"
                if not seed.exists():
                    return
                remote_data = seed.read_bytes()
                put_file(_DB_KEY, remote_data, "Initialize fleet state database")
            if remote_data:
                _LOCAL_DB.write_bytes(remote_data)
        _restore_uploads()
    except Exception as error:
        _warn(error, ui=False)

    # حتى لو فشل تحميل النسخة البعيدة، نفضل نستخدم آخر نسخة محلية معروفة.
    if _LOCAL_DB.exists():
        os.environ["FLEET_DB_PATH"] = str(_LOCAL_DB)


def retry_pending() -> None:
    """إعادة محاولة أي رففعت فشلت، بحد أدنى فاصل بين المحاولات."""
    global _last_retry
    if not enabled() or not (_pending_push or _pending_uploads):
        return
    now = time.monotonic()
    if now - _last_retry < 30:
        return
    _last_retry = now
    if _pending_push:
        push_db()
    for relative_path in list(_pending_uploads):
        push_upload(relative_path)


def push_db() -> None:
    """يرفع قاعدة البيانات بعد أي تعديل، مع تجنّب الرفع المتكرر."""
    global _last_db_hash, _pending_push
    if not enabled() or not _LOCAL_DB.exists():
        return

    data = _LOCAL_DB.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest == _last_db_hash:
        _pending_push = False
        return
    try:
        _, sha = get_file(_DB_KEY)
        put_file(_DB_KEY, data, "Sync fleet database state", sha)
        _last_db_hash = digest
        _pending_push = False
    except Exception as error:
        _pending_push = True
        _warn(error)


def push_upload(relative_path: str) -> None:
    """يرفع ملفاً مرفوعاً ويضيفه لقائمة الملفات في فرع الحالة."""
    global _pending_uploads
    if not enabled():
        return
    local = (_BASE_DIR / relative_path).resolve()
    if not local.is_relative_to(_BASE_DIR) or not local.is_file():
        return

    relative_path = local.relative_to(_BASE_DIR).as_posix()
    key = f"{_UPLOADS_PREFIX}/{relative_path}"
    try:
        _, sha = get_file(key)
        put_file(key, local.read_bytes(), f"Sync upload {relative_path}", sha)

        manifest, manifest_sha = get_file(_MANIFEST_KEY)
        files: list[str] = []
        if manifest:
            try:
                files = list(json.loads(manifest).get("files", []))
            except (ValueError, TypeError):
                files = []
        if relative_path not in files:
            files.append(relative_path)
            put_file(
                _MANIFEST_KEY,
                json.dumps({"files": files}).encode("utf-8"),
                "Update upload manifest",
                manifest_sha,
            )
        _pending_uploads.discard(relative_path)
    except Exception as error:
        _pending_uploads.add(relative_path)
        _warn(error)


def _warn(error: object, *, ui: bool = True) -> None:
    global _STATE_ERROR
    _STATE_ERROR = str(error)
    if ui:
        try:
            import streamlit as st

            st.warning(f"تعذرت مزامنة البيانات مع GitHub: {error}")
            return
        except Exception:
            pass
    print(f"[cloud_sync] {error}")
