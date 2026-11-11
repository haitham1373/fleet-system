"""دوال مساعدة عامة: نصوص، تواريخ، مبالغ، وملفات مرفوعة."""

from __future__ import annotations

import calendar
import html
import mimetypes
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    BASE_DIR,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
    UPLOAD_DIRS,
)

ARABIC_MONTHS = [
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
]


# ---------------------------------------------------------------------------
# النصوص
# ---------------------------------------------------------------------------
def esc(value: object) -> str:
    """يهرب النصوص قبل وضعها داخل HTML."""
    return html.escape("" if value is None else str(value))


def clean_text(value: object, max_length: int = 200) -> str:
    """ينظف النص من الأحرف غير المرئية والمسافات الزائدة ويحد طوله."""
    if value is None:
        return ""

    text = str(value)
    text = "".join(
        character
        for character in text
        if unicodedata.category(character)[0] != "C"
        or character in "\n\t"
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]


def clean_multiline(value: object, max_length: int = 2000) -> str:
    """مثل clean_text لكنه يحافظ على أسطر الملاحظات."""
    if value is None:
        return ""

    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character
        for character in text
        if unicodedata.category(character)[0] != "C" or character in "\n\t"
    )
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)[:max_length]


# ---------------------------------------------------------------------------
# التواريخ
# ---------------------------------------------------------------------------
def parse_date(value: object) -> date | None:
    """يحول القيم المخزنة في قاعدة البيانات إلى تاريخ."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None

    text = str(value).strip().split(" ")[0].split("T")[0]
    if not text:
        return None

    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def format_date(value: object, default: str = "—") -> str:
    parsed = parse_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed else default


def days_until(value: object) -> int | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    return (parsed - date.today()).days


def add_months(value: object, months: int) -> date | None:
    """يضيف عدداً من الأشهر إلى تاريخ مع معالجة نهاية الشهر."""
    parsed = parse_date(value)
    if parsed is None:
        return None

    month_index = parsed.month - 1 + int(months)
    year = parsed.year + month_index // 12
    month = month_index % 12 + 1
    day = min(parsed.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_name_ar(value: object) -> str:
    parsed = parse_date(value)
    if parsed is None:
        return "—"
    return ARABIC_MONTHS[parsed.month - 1]


# ---------------------------------------------------------------------------
# الحالات
# ---------------------------------------------------------------------------
def _missing_days(days: object) -> bool:
    """يكتشف القيم الفارغة بما فيها NaN القادمة من pandas."""
    if days is None:
        return True
    try:
        return bool(days != days)  # NaN لا يساوي نفسه
    except (TypeError, ValueError):
        return True


def maintenance_status(days: int | float | None) -> str:
    if _missing_days(days):
        return "غير محدد"
    if days < 0:
        return "صيانة متأخرة"
    if days <= 10:
        return "صيانة عاجلة"
    if days <= 30:
        return "صيانة قادمة"
    return "الحالة ممتازة"


def inspection_status(days: int | float | None) -> str:
    if _missing_days(days):
        return "غير محدد"
    if days < 0:
        return "منتهي"
    if days <= 30:
        return "قريب الانتهاء"
    return "ساري"


def warranty_status(days: int | float | None) -> str:
    if _missing_days(days):
        return "غير محدد"
    if days < 0:
        return "خارج الضمان"
    if days <= 30:
        return "قريب الانتهاء"
    return "داخل الضمان"


def status_color(status: str) -> str:
    """يرجع لون Streamlit المناسب لحالة نصية."""
    if status in {"منتهي", "صيانة متأخرة", "خارج الضمان", "غير مدفوع", "لم يجتز"}:
        return "red"
    if status in {"صيانة عاجلة", "قريب الانتهاء", "يحتاج إصلاحات"}:
        return "orange"
    if status in {"صيانة قادمة"}:
        return "yellow"
    if status in {"ساري", "داخل الضمان", "مدفوع", "الحالة ممتازة", "اجتاز بنجاح"}:
        return "green"
    return "gray"


# ---------------------------------------------------------------------------
# الأرقام والمبالغ
# ---------------------------------------------------------------------------
def money(value: object, currency: str = "ريال") -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:,.2f} {currency}"


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# الملفات
# ---------------------------------------------------------------------------
def _clean_token(value: object, max_length: int = 40) -> str:
    text = re.sub(r"[^\w\-]+", "_", str(value), flags=re.UNICODE).strip("_")
    return text[:max_length] or "file"


def safe_filename(prefix: str, original_name: str) -> str:
    """ينشئ اسم ملف آمن وفريد مع الحفاظ على الامتداد المسموح."""
    original = os.path.basename(str(original_name or "file"))
    stem, extension = os.path.splitext(original)
    extension = extension.lower()

    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = "، ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise ValueError(f"نوع الملف غير مسموح. الأنواع المسموحة: {allowed}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{_clean_token(prefix)}_{timestamp}_{_clean_token(stem)}{extension}"


def save_upload(folder_key: str, prefix: str, uploaded) -> str:
    """يحفظ ملفاً مرفوعاً بأمان ويرجع مساره النسبي داخل المشروع."""
    if uploaded is None:
        return ""

    size = getattr(uploaded, "size", None)
    if size is None:
        try:
            size = len(uploaded.getbuffer())
        except Exception:
            size = 0

    if size and size > MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(f"حجم الملف يتجاوز الحد المسموح ({MAX_UPLOAD_SIZE_MB} ميجابايت).")

    folder = UPLOAD_DIRS.get(folder_key)
    if folder is None:
        folder = BASE_DIR / folder_key
    folder.mkdir(parents=True, exist_ok=True)

    filename = safe_filename(prefix, uploaded.name)
    destination = (folder / filename).resolve()

    if not destination.is_relative_to(folder.resolve()):
        raise ValueError("مسار الملف غير صالح.")

    destination.write_bytes(uploaded.getbuffer())
    return destination.relative_to(BASE_DIR).as_posix()


def resolve_stored_file(stored_path: object) -> Path | None:
    """يرجع مساراً مطلقاً للملف المخزن إن كان موجوداً."""
    if not stored_path:
        return None

    path = Path(str(stored_path))
    if not path.is_absolute():
        path = BASE_DIR / path
    path = path.resolve()
    return path if path.is_file() else None


def file_bytes(stored_path: object) -> bytes | None:
    path = resolve_stored_file(stored_path)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def mime_for(path: Path | str) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def csv_bytes(dataframe: pd.DataFrame) -> bytes:
    """يصدّر البيانات بصيغة CSV متوافقة مع Excel العربي."""
    return dataframe.to_csv(index=False).encode("utf-8-sig")


def date_range_label(start: date | None, end: date | None) -> str:
    if start and end:
        return f"من {start:%Y-%m-%d} إلى {end:%Y-%m-%d}"
    return "كل الفترات"


def first_day_of_month(value: date | None = None) -> date:
    value = value or date.today()
    return value.replace(day=1)


def days_between(start: object, end: object) -> int | None:
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


def shift_days(value: object, days: int) -> date | None:
    parsed = parse_date(value)
    return parsed + timedelta(days=days) if parsed else None
