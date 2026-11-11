"""النسخ الاحتياطي: إنشاء وتنزيل واستعادة قاعدة بيانات النظام (مدير فقط)."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core import auth, db, ui
from core.config import BACKUP_DIR, DB_PATH

auth.require_admin()
ui.page_header(
    "النسخ الاحتياطي",
    "حماية بيانات الأسطول وإنشاء نسخ آمنة واستعادتها عند الحاجة",
    "💾",
)


def human_size(size: int) -> str:
    """يحول حجم الملف إلى وحدة مقروءة."""
    value = float(size)
    for unit in ("بايت", "كيلوبايت", "ميجابايت", "جيجابايت"):
        if value < 1024 or unit == "جيجابايت":
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} جيجابايت"


def database_snapshot_bytes() -> bytes:
    """يرجع نسخة متسقة من قاعدة البيانات الحالية دون ترك ملفات مؤقتة.

    القراءة المباشرة لملف ``fleet.db`` قد تتجاهل صفحات WAL غير المُدمجة،
    لذلك نستخدم واجهة SQLite الرسمية لأخذ لقطة متسقة ثم نقرأ بايتاتها.
    """
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".db",
            delete=False,
            dir=tempfile.gettempdir(),
        ) as temporary:
            temp_path = Path(temporary.name)

        source = sqlite3.connect(str(DB_PATH), timeout=30.0)
        target = sqlite3.connect(str(temp_path))
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        return temp_path.read_bytes()
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def backup_files() -> list[Path]:
    """جميع ملفات النسخ الاحتياطي مرتبة من الأحدث."""
    if not BACKUP_DIR.is_dir():
        return []
    return sorted(
        (path for path in BACKUP_DIR.glob("*.db") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


backups = backup_files()
db_size = db.database_size_bytes()
last_backup = (
    datetime.fromtimestamp(backups[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    if backups
    else "—"
)

metric_columns = st.columns(3)
metric_columns[0].metric("حجم قاعدة البيانات", human_size(db_size))
metric_columns[1].metric("عدد النسخ الاحتياطية", f"{len(backups):,}")
metric_columns[2].metric("آخر نسخة احتياطية", last_backup)
st.write("")

# ---------------------------------------------------------------------------
# إنشاء نسخة احتياطية
# ---------------------------------------------------------------------------
st.markdown("#### إنشاء نسخة احتياطية جديدة")
create_column, download_column = st.columns(2)

with create_column:
    if st.button(
        "💾 إنشاء نسخة احتياطية الآن",
        type="primary",
        width="stretch",
        key="create_backup_button",
    ):
        try:
            destination = db.create_server_backup()
            db.log_audit(
                auth.current_username(),
                "نسخ احتياطي",
                "قاعدة البيانات",
                destination.name,
            )
            st.success(f"تم إنشاء النسخة الاحتياطية: {destination.name}")
            st.rerun()
        except Exception as error:
            st.error(f"تعذر إنشاء النسخة الاحتياطية: {error}")

with download_column:
    if DB_PATH.is_file():
        try:
            snapshot_bytes = database_snapshot_bytes()
        except Exception as error:
            st.error(f"تعذر تجهيز نسخة للتنزيل: {error}")
        else:
            st.download_button(
                "⬇️ تنزيل قاعدة البيانات الحالية",
                data=snapshot_bytes,
                file_name=f"fleet_backup_{datetime.now():%Y-%m-%d_%H-%M-%S}.db",
                mime="application/octet-stream",
                width="stretch",
                key="download_current_db",
            )
    else:
        st.warning("ملف قاعدة البيانات غير موجود.")

st.divider()

# ---------------------------------------------------------------------------
# النسخ المتاحة
# ---------------------------------------------------------------------------
ui.section_title("النسخ الاحتياطية المتاحة", "اختر نسخة لتنزيلها على جهازك")

if not backups:
    ui.empty_state("لا توجد نسخ احتياطية بعد.", "💾")
else:
    backup_rows = []
    for path in backups:
        try:
            stats = path.stat()
        except OSError:
            continue
        backup_rows.append(
            {
                "الملف": path.name,
                "الحجم": human_size(stats.st_size),
                "تاريخ الإنشاء": datetime.fromtimestamp(
                    stats.st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    backups_frame = pd.DataFrame(backup_rows)
    ui.render_df(
        backups_frame,
        alt="جدول النسخ الاحتياطية",
    )

    selected_backup_name = st.selectbox(
        "اختر نسخة للتنزيل",
        [path.name for path in backups],
        key="selected_backup_download",
    )
    selected_backup = BACKUP_DIR / selected_backup_name
    if selected_backup.is_file():
        st.download_button(
            f"⬇️ تنزيل {selected_backup_name}",
            data=selected_backup.read_bytes(),
            file_name=selected_backup_name,
            mime="application/octet-stream",
            width="stretch",
            key="download_selected_backup",
        )

st.divider()

# ---------------------------------------------------------------------------
# الاستعادة
# ---------------------------------------------------------------------------
ui.section_title("استعادة قاعدة البيانات", "استبدال البيانات الحالية بنسخة احتياطية موثوقة")

st.warning(
    "الاستعادة تستبدل جميع البيانات الحالية. سيتم إنشاء نسخة أمان تلقائية "
    "قبل التنفيذ، وسيُطلب منك تسجيل الدخول من جديد."
)

uploaded_backup = st.file_uploader(
    "ملف النسخة الاحتياطية (.db)",
    type=["db"],
    key="restore_backup_upload",
)

if uploaded_backup is not None:
    size = getattr(uploaded_backup, "size", 0) or 0
    st.caption(f"الملف المحدد: {uploaded_backup.name} • {human_size(size)}")

confirm_restore = st.checkbox(
    "أؤكد رغبتي في استعادة هذه النسخة واستبدال البيانات الحالية",
    key="confirm_restore_backup",
)

restore_disabled = uploaded_backup is None or not confirm_restore
if st.button(
    "♻️ استعادة النسخة الاحتياطية",
    type="secondary",
    width="stretch",
    disabled=restore_disabled,
    key="restore_backup_button",
):
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".db",
            delete=False,
            dir=tempfile.gettempdir(),
        ) as temporary:
            temporary.write(uploaded_backup.getbuffer())
            temp_path = Path(temporary.name)

        connection = sqlite3.connect(str(temp_path))
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]).lower() != "ok":
                raise ValueError("ملف قاعدة البيانات تالف أو غير صالح.")

            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {"Users", "Buses", "Logs"}
            missing = required - tables
            if missing:
                raise ValueError(
                    "الملف لا يحتوي على جداول النظام المطلوبة: "
                    + "، ".join(sorted(missing))
                )
        finally:
            connection.close()

        safety_backup = db.restore_from_file(temp_path)
        db.log_audit(
            auth.current_username(),
            "استعادة",
            "قاعدة البيانات",
            uploaded_backup.name,
            f"نسخة الأمان: {safety_backup.name}",
        )
        auth.logout()
        st.session_state["flash_message"] = (
            "تمت استعادة قاعدة البيانات بنجاح. يرجى تسجيل الدخول من جديد. "
            f"نسخة الأمان: {safety_backup.name}"
        )
        st.rerun()
    except ValueError as error:
        st.error(str(error))
    except Exception as error:
        st.error(f"تعذر استعادة النسخة الاحتياطية: {error}")
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
