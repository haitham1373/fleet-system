"""إعدادات النظام والمسارات الثابتة."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# المسارات الأساسية
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(
    os.environ.get("FLEET_DB_PATH", str(BASE_DIR / "fleet.db"))
).resolve()

LOGO_PATH = BASE_DIR / "logo.png"
# نسخة دائرية شفافة من الشعار تُستخدم في الواجهة لإظهاره بإطار أنيق.
LOGO_CIRCLE_PATH = BASE_DIR / "logo_circle.png"
FALLBACK_LOGO_PATH = BASE_DIR / "rtrgrfwerfr3g.jpeg"
BACKUP_DIR = BASE_DIR / "Backup"

UPLOAD_DIRS: dict[str, Path] = {
    "invoices": BASE_DIR / "uploaded_invoices",
    "batteries": BASE_DIR / "battery_warranties",
    "inspections": BASE_DIR / "inspection_reports",
    "hotel_contracts": BASE_DIR / "hotel_contracts",
    "parking_invoices": BASE_DIR / "parking_invoices",
    "parking_contracts": BASE_DIR / "parking_contracts",
    "parking_bills": BASE_DIR / "parking_bills",
}

# ---------------------------------------------------------------------------
# إعدادات الملفات المرفوعة
# ---------------------------------------------------------------------------
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_UPLOAD_SIZE_MB = int(os.environ.get("FLEET_MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ---------------------------------------------------------------------------
# هوية النظام
# ---------------------------------------------------------------------------
APP_TITLE = "نظام إدارة الأسطول - شركة بروج العالم"
COMPANY_NAME = "شركة بروج العالم للنقل"
COMPANY_SUBTITLE = "نظام إدارة المركبات والصيانة والبطاريات والفحص الدوري والعقود"
APP_VERSION = "2.0"

# ---------------------------------------------------------------------------
# إعدادات الأمان
# ---------------------------------------------------------------------------
SESSION_TIMEOUT_HOURS = int(os.environ.get("FLEET_SESSION_HOURS", "8"))
PBKDF2_ITERATIONS = int(os.environ.get("FLEET_PBKDF2_ITERATIONS", "240000"))
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 5


def ensure_directories() -> None:
    """ينشئ مجلدات التخزين المطلوبة إن لم تكن موجودة."""
    for folder in (BACKUP_DIR, *UPLOAD_DIRS.values()):
        folder.mkdir(parents=True, exist_ok=True)
