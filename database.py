"""وحدة توافقية للواجهات القديمة.

النظام الجديد يستخدم :mod:`core.db` و:mod:`core.security` و:mod:`core.utils`
مباشرة. هذا الملف يبقي الاستيرادات القديمة تعمل دون تنفيذ أي كود واجهة أو
إنشاء قاعدة بيانات عند الاستيراد.
"""

from __future__ import annotations

from core import db as _db
from core.config import DB_PATH
from core.security import hash_password, verify_password
from core.utils import esc, save_upload


def init_db() -> None:
    """ينشئ قاعدة البيانات ويرحّل البيانات القديمة بأمان."""
    _db.init_db()


def get_conn():
    """اتصال آمن بقاعدة البيانات (سياق إدارة)."""
    return _db.get_conn()


def fetch_all(sql: str, params=()):
    return _db.fetch_all(sql, params)


def fetch_one(sql: str, params=()):
    return _db.fetch_one(sql, params)


def execute(sql: str, params=()):
    return _db.execute(sql, params)


__all__ = [
    "DB_PATH",
    "esc",
    "execute",
    "fetch_all",
    "fetch_one",
    "get_conn",
    "hash_password",
    "init_db",
    "save_upload",
    "verify_password",
]
