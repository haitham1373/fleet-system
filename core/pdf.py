"""توليد تقارير PDF عربية بأسلوب احترافي متوافق مع الهوية البصرية الجديدة.

يعتمد على ReportLab مع دعم تشكيل الحروف العربية واتجاه النص من اليمين
إلى اليسار عبر ``arabic_reshaper`` و``python-bidi``. تم توحيد ألوان
التقارير مع تجديد الواجهة: أخضر مؤسسي، لمسة ذهبية، بطاقات واضحة
وجداول متباعدة تصلح للطباعة المكتبية بالأبيض والأسود.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .config import BASE_DIR, LOGO_CIRCLE_PATH, LOGO_PATH

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 14 * mm
MARGIN_Y = 12 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

# ---------------------------------------------------------------------------
# هوية التصميم (مطابقة لواجهة التطبيق بعد التجديد)
# ---------------------------------------------------------------------------
BRAND_800 = colors.HexColor("#2f7d5c")
BRAND_700 = colors.HexColor("#2f7d5c")
BRAND_600 = colors.HexColor("#2f7d5c")
BRAND_INK = colors.HexColor("#0d3326")
PRIMARY = BRAND_700
PRIMARY_LIGHT = BRAND_600
PRIMARY_SOFT = colors.HexColor("#eaf5ef")
ACCENT = colors.HexColor("#9a6b1d")
ACCENT_SOFT = colors.HexColor("#fbf3e4")
DARK = colors.HexColor("#0f172a")
TEXT = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#1f2937")
BORDER = colors.HexColor("#e2e8f0")
INFO_BG = colors.HexColor("#f8fafc")
SUCCESS = colors.HexColor("#166534")
SUCCESS_BG = colors.HexColor("#dcfce7")
WARNING = colors.HexColor("#92400e")
DANGER = colors.HexColor("#991b1b")
DANGER_BG = colors.HexColor("#fee2e2")

# ألوان نموذج «كشف التفويج» المعتمد (أخضر رسمي + ذهبي)
REF_GREEN = colors.HexColor("#0f4c3a")
REF_GOLD = colors.HexColor("#9a6b1d")
REF_GRID = colors.HexColor("#cbd5e1")
REF_ROW_GREEN = colors.HexColor("#f1f5f4")
REF_ROW_BLUE = colors.HexColor("#f8fafc")

COMPANY_NAME_AR = "شركة بروج العالم للنقل"
COMPANY_NAME_AR_LINE2 = "البري"
COMPANY_NAME_EN = "Burooj Al-Alam Land Transport"
COMPANY_NAME_EN_LINE2 = "Company"
COMPANY_TAGLINE = "نظام إدارة الأسطول والصيانة"
FOOTER_AR = (
    "( سنترال ) مكة المكرمة – بطحاء قريش – الشارع العام – تلفون : "
    "\u202a+966 2 5771177\u202c – فاكس : \u202a+966 2 5729455\u202c – ص.ب : 5941"
)
FOOTER_EN = (
    "Makkah Al-Mukaramah – main road – Bathaa Quraish – Tel : "
    "+966 2 5771177 – Fax : +966 2 5729455 – P.O.Box : 5941"
)
FOOTER_EMAIL = "broujalalam@hotmail.com"


# ---------------------------------------------------------------------------
# هويات الشركات التي يمكن إصدار التقرير الشامل باسمها
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CompanyProfile:
    key: str
    label: str
    name_ar: str
    name_ar_line2: str
    name_en: str
    name_en_line2: str
    tagline: str
    logo_files: tuple[Path, ...]
    footer_ar: str
    footer_en: str
    footer_email: str


HOSPITALITY_LOGO_PATH = BASE_DIR / "hospitality_logo.png"

COMPANY_PROFILES: dict[str, CompanyProfile] = {
    "burooj": CompanyProfile(
        key="burooj",
        label="شركة بروج العالم للنقل",
        name_ar=COMPANY_NAME_AR,
        name_ar_line2=COMPANY_NAME_AR_LINE2,
        name_en=COMPANY_NAME_EN,
        name_en_line2=COMPANY_NAME_EN_LINE2,
        tagline=COMPANY_TAGLINE,
        logo_files=(LOGO_CIRCLE_PATH, LOGO_PATH),
        footer_ar=FOOTER_AR,
        footer_en=FOOTER_EN,
        footer_email=FOOTER_EMAIL,
    ),
    "hospitality": CompanyProfile(
        key="hospitality",
        label="مجموعة الضيافة العالمية",
        name_ar="مجموعة الضيافة العالمية",
        name_ar_line2="",
        name_en="Deafah International Group",
        name_en_line2="",
        tagline=COMPANY_TAGLINE,
        logo_files=(
            BASE_DIR / "Deafah.jpeg",
            HOSPITALITY_LOGO_PATH,
            BASE_DIR / "logo_hospitality.png",
        ),
        footer_ar=(
            "مكة المكرمة – تلفون : +966 2 5771177 – فاكس : +966 2 5729455 "
            "– ص.ب : 5941 – الحجز والمبيعات : +966 2 5729355"
        ),
        footer_en=(
            "MAKKAH – TEL : +966 2 5771177 – FAX : +966 2 5729455 "
            "– P.O.BOX : 5941 – RESERVATION & SALES : +966 2 5729355"
        ),
        footer_email="",
    ),
}

DEFAULT_COMPANY_KEY = "burooj"


def company_profile(key: str | CompanyProfile | None = None) -> CompanyProfile:
    """يعيد هوية الشركة المطلوبة، ويرجع لبروج عند أي قيمة غير معروفة."""
    if isinstance(key, CompanyProfile):
        return key
    return COMPANY_PROFILES.get(str(key or ""), COMPANY_PROFILES[DEFAULT_COMPANY_KEY])


_FONT_CACHE: tuple[str, str] | None = None


# ---------------------------------------------------------------------------
# الخطوط وتشكيل النص
# ---------------------------------------------------------------------------
def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def register_fonts() -> tuple[str, str]:
    """يسجّل خطاً عربياً عادياً وآخر عريضاً ويعيد اسميهما."""
    global _FONT_CACHE
    if _FONT_CACHE:
        return _FONT_CACHE

    windows_fonts = Path("C:/Windows/Fonts")
    regular = _first_existing(
        [
            windows_fonts / "tahoma.ttf",
            BASE_DIR / "Cairo-Regular.ttf",
            BASE_DIR / "Amiri-Regular.ttf",
        ]
    )
    bold = _first_existing(
        [
            windows_fonts / "tahomabd.ttf",
            BASE_DIR / "Cairo-Bold.ttf",
            BASE_DIR / "Amiri-Bold.ttf",
            BASE_DIR / "Amiri-Regular.ttf",
        ]
    )
    if regular is None:
        raise RuntimeError("لم يتم العثور على خط عربي لتوليد ملف PDF.")

    pdfmetrics.registerFont(TTFont("ArabicBody", str(regular)))
    pdfmetrics.registerFont(TTFont("ArabicBold", str(bold or regular)))
    _FONT_CACHE = ("ArabicBody", "ArabicBold")
    return _FONT_CACHE


def ltr(text: object) -> str:
    """يغلّف مقطعاً لاتينياً/رقمياً بعلامات اتجاه ليبقى ترتيبه صحيحاً."""
    return f"\u202a{text}\u202c"


def rtl(text: object) -> str:
    """يعيد النص مشكّلاً بترتيب العرض الصحيح للعربية."""
    value = "" if text is None else str(text)
    if not value.strip():
        return ""
    try:
        return get_display(arabic_reshaper.reshape(value))
    except Exception:
        return value


def _display_value(value: object) -> str:
    """يعيد قيمة مقروءة للحقول الفارغة بدل ترك خلايا بيضاء."""
    text = "" if value is None else str(value).strip()
    return text if text else "—"


def _field_markup(label: str, value: object, bold_font: str) -> str:
    """ينشئ نص الحقل بعنوان عريض ملوّن وقيمة واضحة مع ترتيب الأرقام."""
    label_visual = rtl(label)
    value_visual = rtl(_display_value(value))
    bold_label = (
        f'<font name="{bold_font}" color="#0d3326">'
        f"{xml_escape(label_visual)}</font>"
    )
    return f"{xml_escape(value_visual)} {bold_label}"


# ---------------------------------------------------------------------------
# الأنماط
# ---------------------------------------------------------------------------
def _styles() -> dict[str, ParagraphStyle]:
    body_font, bold_font = register_fonts()
    return {
        "body": ParagraphStyle(
            "body",
            fontName=body_font,
            fontSize=9.5,
            leading=14,
            alignment=TA_RIGHT,
            textColor=TEXT,
        ),
        "body_center": ParagraphStyle(
            "body_center",
            fontName=body_font,
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=TEXT,
        ),
        "brand_ar": ParagraphStyle(
            "brand_ar",
            fontName=bold_font,
            fontSize=14,
            leading=18,
            alignment=TA_RIGHT,
            textColor=BRAND_INK,
        ),
        "brand_ar_small": ParagraphStyle(
            "brand_ar_small",
            fontName=body_font,
            fontSize=8.5,
            leading=12,
            alignment=TA_RIGHT,
            textColor=BRAND_INK,
        ),
        "brand_en": ParagraphStyle(
            "brand_en",
            fontName=bold_font,
            fontSize=9,
            leading=13,
            alignment=TA_LEFT,
            textColor=BRAND_INK,
        ),
        "brand_en_small": ParagraphStyle(
            "brand_en_small",
            fontName=body_font,
            fontSize=7.8,
            leading=11,
            alignment=TA_LEFT,
            textColor=BRAND_INK,
        ),
        "doc_title": ParagraphStyle(
            "doc_title",
            fontName=bold_font,
            fontSize=15,
            leading=20,
            alignment=TA_RIGHT,
            textColor=BRAND_INK,
            keepWithNext=True,
        ),
        "doc_subtitle": ParagraphStyle(
            "doc_subtitle",
            fontName=body_font,
            fontSize=9,
            leading=13,
            alignment=TA_RIGHT,
            textColor=MUTED,
        ),
        "doc_ref": ParagraphStyle(
            "doc_ref",
            fontName=body_font,
            fontSize=8.5,
            leading=12,
            alignment=TA_LEFT,
            textColor=MUTED,
        ),
        "field": ParagraphStyle(
            "field",
            fontName=body_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_RIGHT,
            textColor=TEXT,
        ),
        "table_head": ParagraphStyle(
            "table_head",
            fontName=bold_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            fontName=body_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=DARK,
        ),
        "table_index": ParagraphStyle(
            "table_index",
            fontName=bold_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "section_title": ParagraphStyle(
            "section_title",
            fontName=bold_font,
            fontSize=11,
            leading=15,
            alignment=TA_RIGHT,
            textColor=BRAND_INK,
            keepWithNext=True,
        ),
        "section_bar": ParagraphStyle(
            "section_bar",
            fontName=bold_font,
            fontSize=10,
            leading=14,
            alignment=TA_RIGHT,
            textColor=BRAND_INK,
            keepWithNext=True,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName=body_font,
            fontSize=8.5,
            leading=12,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName=bold_font,
            fontSize=13,
            leading=17,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "total": ParagraphStyle(
            "total",
            fontName=bold_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "grand_total": ParagraphStyle(
            "grand_total",
            fontName=bold_font,
            fontSize=13,
            leading=18,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "signature": ParagraphStyle(
            "signature",
            fontName=bold_font,
            fontSize=11,
            leading=16,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "signature_name": ParagraphStyle(
            "signature_name",
            fontName=bold_font,
            fontSize=13,
            leading=18,
            alignment=TA_CENTER,
            textColor=BRAND_INK,
        ),
        "footer_ar": ParagraphStyle(
            "footer_ar",
            fontName=body_font,
            fontSize=7.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "footer_en": ParagraphStyle(
            "footer_en",
            fontName=body_font,
            fontSize=7.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "footer_page": ParagraphStyle(
            "footer_page",
            fontName=bold_font,
            fontSize=8,
            leading=11,
            alignment=TA_LEFT,
            textColor=BRAND_INK,
        ),
        "empty": ParagraphStyle(
            "empty",
            fontName=body_font,
            fontSize=10,
            leading=16,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "status_ok": ParagraphStyle(
            "status_ok",
            fontName=bold_font,
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=SUCCESS,
            backColor=SUCCESS_BG,
            borderColor=SUCCESS,
            borderWidth=0.4,
            borderPadding=3,
        ),
        "status_warn": ParagraphStyle(
            "status_warn",
            fontName=bold_font,
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=WARNING,
            backColor=ACCENT_SOFT,
            borderColor=ACCENT,
            borderWidth=0.4,
            borderPadding=3,
        ),
        "status_bad": ParagraphStyle(
            "status_bad",
            fontName=bold_font,
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=DANGER,
            backColor=DANGER_BG,
            borderColor=DANGER,
            borderWidth=0.4,
            borderPadding=3,
        ),
        # أنماط بيان الركاب بنموذج كشف التفويج المعتمد
        "mf_company_ar": ParagraphStyle(
            "mf_company_ar",
            fontName=bold_font,
            fontSize=15,
            leading=20,
            alignment=TA_RIGHT,
            textColor=REF_GREEN,
        ),
        "mf_company_ar_sub": ParagraphStyle(
            "mf_company_ar_sub",
            fontName=bold_font,
            fontSize=10.5,
            leading=14,
            alignment=TA_RIGHT,
            textColor=REF_GOLD,
        ),
        "mf_company_en": ParagraphStyle(
            "mf_company_en",
            fontName=bold_font,
            fontSize=10.5,
            leading=14,
            alignment=TA_LEFT,
            textColor=REF_GREEN,
        ),
        "mf_company_en_sub": ParagraphStyle(
            "mf_company_en_sub",
            fontName=body_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_LEFT,
            textColor=MUTED,
        ),
        "mf_title": ParagraphStyle(
            "mf_title",
            fontName=bold_font,
            fontSize=15,
            leading=20,
            alignment=TA_RIGHT,
            textColor=REF_GREEN,
        ),
        "mf_ref": ParagraphStyle(
            "mf_ref",
            fontName=bold_font,
            fontSize=10.5,
            leading=14,
            alignment=TA_LEFT,
            textColor=REF_GOLD,
        ),
        "mf_section": ParagraphStyle(
            "mf_section",
            fontName=bold_font,
            fontSize=12.5,
            leading=17,
            alignment=TA_RIGHT,
            textColor=REF_GREEN,
            keepWithNext=True,
        ),
        "mf_label": ParagraphStyle(
            "mf_label",
            fontName=bold_font,
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
            textColor=REF_GREEN,
        ),
        "mf_value": ParagraphStyle(
            "mf_value",
            fontName=body_font,
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
            textColor=DARK,
        ),
        "mf_table_head": ParagraphStyle(
            "mf_table_head",
            fontName=bold_font,
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
        "mf_table_cell": ParagraphStyle(
            "mf_table_cell",
            fontName=body_font,
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=DARK,
        ),
        "mf_index": ParagraphStyle(
            "mf_index",
            fontName=bold_font,
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=REF_GREEN,
        ),
        "mf_sig_label": ParagraphStyle(
            "mf_sig_label",
            fontName=bold_font,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=REF_GREEN,
        ),
        "mf_sig_name": ParagraphStyle(
            "mf_sig_name",
            fontName=body_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "mf_footer_ar": ParagraphStyle(
            "mf_footer_ar",
            fontName=body_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=TEXT,
        ),
        "mf_footer_en": ParagraphStyle(
            "mf_footer_en",
            fontName=body_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "mf_footer_bottom": ParagraphStyle(
            "mf_footer_bottom",
            fontName=bold_font,
            fontSize=8.5,
            leading=12,
            alignment=TA_RIGHT,
            textColor=REF_GREEN,
        ),
        "mf_footer_page": ParagraphStyle(
            "mf_footer_page",
            fontName=body_font,
            fontSize=8.5,
            leading=12,
            alignment=TA_LEFT,
            textColor=MUTED,
        ),
    }


# ---------------------------------------------------------------------------
# مكوّنات مشتركة
# ---------------------------------------------------------------------------
def _logo_path(profile: CompanyProfile | None = None) -> Path | None:
    active = profile or company_profile()
    for candidate in active.logo_files:
        if candidate.is_file():
            return candidate
    return None


def _header(
    styles: dict[str, ParagraphStyle],
    *,
    title: str,
    subtitle: str,
    reference: str,
    profile: CompanyProfile | None = None,
) -> list:
    """يبني رأس التقرير: شريط هوية + بطاقة عنوان بلمسة ذهبية."""
    active = profile or company_profile()
    arabic_lines = [rtl(active.name_ar)]
    if active.name_ar_line2:
        arabic_lines.append(rtl(active.name_ar_line2))
    arabic = Paragraph("<br/>".join(arabic_lines), styles["brand_ar"])
    arabic_tag = Paragraph(rtl(active.tagline), styles["brand_ar_small"])
    english_lines = [active.name_en]
    if active.name_en_line2:
        english_lines.append(active.name_en_line2)
    english = Paragraph("<br/>".join(english_lines), styles["brand_en"])

    logo: object = ""
    path = _logo_path(active)
    if path is not None:
        image = Image(str(path))
        image.drawWidth = 56
        image.drawHeight = 56
        logo = image

    identity = Table(
        [[english, logo, [arabic, arabic_tag]]],
        colWidths=[CONTENT_WIDTH * 0.36, CONTENT_WIDTH * 0.22, CONTENT_WIDTH * 0.42],
    )
    identity.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_SOFT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    title_text = Paragraph(rtl(title), styles["doc_title"])
    subtitle_text = Paragraph(rtl(subtitle), styles["doc_subtitle"])
    ref_text = Paragraph(rtl(reference), styles["doc_ref"])
    date_text = Paragraph(rtl(f"تاريخ الإصدار: {date.today():%d-%m-%Y}"), styles["doc_ref"])

    title_card = Table(
        [
            [ref_text, title_text],
            [date_text, subtitle_text],
        ],
        colWidths=[CONTENT_WIDTH * 0.32, CONTENT_WIDTH * 0.68],
    )
    title_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("LINEAFTER", (1, 0), (1, -1), 3, ACCENT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.4, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    accent_line = HRFlowable(
        width="100%",
        thickness=2,
        color=ACCENT,
        spaceBefore=0,
        spaceAfter=10,
    )
    return [identity, title_card, accent_line]


FOOTER_RESERVED = 46  # المساحة المحجوزة أسفل كل صفحة للتذييل (بالنقاط)


def _footer_flowables(
    styles: dict[str, ParagraphStyle],
    profile: CompanyProfile | None = None,
) -> list[Paragraph]:
    """فقرات تذييل التقرير (بيانات الشركة) التي تُرسم أسفل كل صفحة."""
    active = profile or company_profile()
    entries = [
        (rtl(active.footer_ar), "footer_ar"),
        (active.footer_en, "footer_en"),
        (active.footer_email, "footer_en"),
    ]
    return [
        Paragraph(text, styles[style])
        for text, style in entries
        if str(text).strip()
    ]


def _frame_canvas(canvas, doc) -> None:
    """يضيف إطاراً كاملاً وشريط هوية أعلى الصفحة."""
    width, height = doc.pagesize
    canvas.saveState()
    inset = 10 * mm
    canvas.setStrokeColor(PRIMARY)
    canvas.setLineWidth(0.8)
    canvas.rect(
        inset,
        inset,
        width - (2 * inset),
        height - (2 * inset),
        stroke=1,
        fill=0,
    )
    canvas.restoreState()


def _footer_callback(
    styles: dict[str, ParagraphStyle],
    profile: CompanyProfile | None = None,
):
    """ينشئ دالة ترسم تذييل الشركة ورقم الصفحة أسفل كل صفحة."""
    paragraphs = _footer_flowables(styles, profile)

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        width, _ = doc.pagesize
        line_y = MARGIN_Y + FOOTER_RESERVED
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_X, line_y, width - MARGIN_X, line_y)
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(width - MARGIN_X - 70, line_y, width - MARGIN_X, line_y)

        y = line_y - 5
        for paragraph in paragraphs:
            _, height = paragraph.wrapOn(canvas, CONTENT_WIDTH, 1000)
            y -= height
            paragraph.drawOn(canvas, MARGIN_X, y)

        page = Paragraph(
            rtl(f"صفحة {canvas.getPageNumber()}"), styles["footer_page"]
        )
        page_width, page_height = page.wrapOn(canvas, 120, 1000)
        page.drawOn(canvas, width - MARGIN_X - page_width, y)
        canvas.restoreState()

    return draw_footer


def _info_table(
    fields: list[tuple[str, object]],
    styles: dict[str, ParagraphStyle],
    bold_font: str,
) -> Table:
    """بطاقة بيانات الهوية: خلفية هادئة وفواصل رقيقة وخطوط عنوان داكنة."""
    rows: list[list[Paragraph]] = []
    for start in range(0, len(fields), 3):
        chunk = fields[start : start + 3]
        chunk += [("", "")] * (3 - len(chunk))
        # نعكس الترتيب لأن أول حقل يجب أن يظهر في العمود الأيمن.
        rows.append(
            [
                Paragraph(_field_markup(label, value, bold_font), styles["field"])
                for label, value in reversed(chunk)
            ]
        )

    table = Table(rows, colWidths=[CONTENT_WIDTH / 3] * 3)
    style = [
        ("BACKGROUND", (0, 0), (-1, -1), INFO_BG),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    if len(rows) > 1:
        style.append(("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER))
    table.setStyle(TableStyle(style))
    return table


def _data_table(
    data: list[list[Paragraph]],
    widths: list[float],
    *,
    header_background: colors.Color = PRIMARY_SOFT,
    row_padding: float = 7,
) -> Table:
    """جدول بيانات موحّد: رأس فاتح، خط ذهبي، صفوف متبادلة وحدود ناعمة."""
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_background),
                ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_INK),
                ("LINEBELOW", (0, 0), (-1, 0), 2.5, ACCENT),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("BOX", (0, 0), (-1, -1), 0.8, PRIMARY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, INFO_BG]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), row_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), row_padding),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _section_header(
    text: str, styles: dict[str, ParagraphStyle]
) -> Table:
    """عنوان مجموعة/مركبة على هيئة شريط أخضر فاتح بلمسة ذهبية."""
    header = Table(
        [[Paragraph(rtl(text), styles["section_title"])]],
        colWidths=[CONTENT_WIDTH],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_SOFT),
                ("LINEAFTER", (0, 0), (-1, -1), 3, ACCENT),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return header


def _content_section(
    text: str, styles: dict[str, ParagraphStyle]
) -> Table:
    """شريط عنوان داكن يفصل أقسام التقرير ويمنحه ترتيباً بصرياً أوضح."""
    bar = Table(
        [[Paragraph(rtl(text), styles["section_bar"])]],
        colWidths=[CONTENT_WIDTH],
    )
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_SOFT),
                ("LINEAFTER", (0, 0), (-1, -1), 3, ACCENT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return bar


def _summary_cards(
    items: list[tuple[str, str]], styles: dict[str, ParagraphStyle]
) -> Table:
    """بطاقات مؤشرات سريعة في أعلى التقرير الشامل."""
    cards: list[Table] = []
    # الترتيب في العرض من اليمين لليسار: أول بطاقة في أقصى اليمين.
    for label, value in reversed(items):
        card = Table(
            [
                [Paragraph(rtl(label), styles["kpi_label"])],
                [Paragraph(rtl(value), styles["kpi_value"])],
            ],
            colWidths=[CONTENT_WIDTH / 3 - 10],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                    ("LINEABOVE", (0, 0), (-1, 0), 3, ACCENT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        cards.append(card)

    row = Table([cards], colWidths=[CONTENT_WIDTH / 3] * 3)
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return row


def _status_paragraph(
    status: object, styles: dict[str, ParagraphStyle]
) -> Paragraph:
    """يعرض حالة السداد كشريحة ملوّنة داخل الخلية."""
    value = str(status or "—").strip() or "—"
    if value in {"غير مدفوع", "متأخر", "لم يجتز", "منتهي", "خارج الضمان"}:
        style = styles["status_bad"]
    elif value in {"مدفوع", "ساري", "اجتاز بنجاح", "داخل الضمان"}:
        style = styles["status_ok"]
    elif value in {"قيد المعالجة", "جزئي", "قريب الانتهاء", "يحتاج إصلاحات"}:
        style = styles["status_warn"]
    else:
        style = styles["table_cell"]
    return Paragraph(rtl(value), style)


def _build_document(
    flowables: list,
    title: str,
    styles: dict[str, ParagraphStyle],
    profile: CompanyProfile | None = None,
) -> bytes:
    active = profile or company_profile()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_Y,
        bottomMargin=MARGIN_Y + FOOTER_RESERVED,
        title=title,
        author=active.name_ar,
    )
    footer = _footer_callback(styles, active)

    def decorate_page(canvas, doc) -> None:
        """يرسم شريط الهوية ثم التذييل في كل صفحة."""
        _frame_canvas(canvas, doc)
        footer(canvas, doc)

    document.build(flowables, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# بيان الركاب (بنموذج كشف التفويج المعتمد)
# ---------------------------------------------------------------------------
MANIFEST_MARGIN_X = 18 * mm
MANIFEST_CONTENT_WIDTH = PAGE_WIDTH - (2 * MANIFEST_MARGIN_X)
MANIFEST_FOOTER_RESERVED = 60


def _manifest_header(
    styles: dict[str, ParagraphStyle], operation_number: str
) -> list:
    """رأس النموذج: اسم الشركة يميناً وترجمتها يساراً، ثم عنوان الكشف."""
    arabic = [
        Paragraph(
            rtl(COMPANY_NAME_AR + " " + COMPANY_NAME_AR_LINE2),
            styles["mf_company_ar"],
        ),
        Paragraph(rtl("لنقل الحجاج والمعتمرين"), styles["mf_company_ar_sub"]),
    ]
    english = [
        Paragraph(COMPANY_NAME_EN + " " + COMPANY_NAME_EN_LINE2, styles["mf_company_en"]),
        Paragraph("Pilgrims & Umrah Transport Services", styles["mf_company_en_sub"]),
    ]
    logo: object = ""
    path = _logo_path()
    if path is not None:
        image = Image(str(path))
        image.drawWidth = 50
        image.drawHeight = 50
        logo = image

    identity = Table(
        [[english, logo, arabic]],
        colWidths=[
            MANIFEST_CONTENT_WIDTH * 0.40,
            MANIFEST_CONTENT_WIDTH * 0.16,
            MANIFEST_CONTENT_WIDTH * 0.44,
        ],
    )
    identity.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    title = Table(
        [
            [
                Paragraph(
                    rtl(f"تشغيلة رقم: {_display_value(operation_number)}"),
                    styles["mf_ref"],
                ),
                Paragraph(rtl("كشف تفويج ونقل ركاب"), styles["mf_title"]),
            ]
        ],
        colWidths=[
            MANIFEST_CONTENT_WIDTH * 0.32,
            MANIFEST_CONTENT_WIDTH * 0.68,
        ],
    )
    title.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, REF_GREEN),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return [identity, Spacer(1, 10), title, Spacer(1, 6)]


def _manifest_info_table(
    fields: list[tuple[str, object]],
    styles: dict[str, ParagraphStyle],
    padding: float = 5,
) -> Table:
    """شبكة بيانات الرحلة: حقلان في كل صف، والعناوين بخلفية خضراء فاتحة."""
    rows: list[list[Paragraph]] = []
    for start in range(0, len(fields), 2):
        chunk = fields[start : start + 2]
        chunk += [("", "")] * (2 - len(chunk))
        cells: list[Paragraph] = []
        # من اليسار إلى اليمين: قيمة الحقل الثاني، عنوانه، قيمة الأول، عنوانه
        for label, value in reversed(chunk):
            cells.append(
                Paragraph(rtl(_display_value(value)), styles["mf_value"])
            )
            cells.append(Paragraph(rtl(label), styles["mf_label"]))
        rows.append(cells)

    widths = [MANIFEST_CONTENT_WIDTH * 0.28, MANIFEST_CONTENT_WIDTH * 0.22] * 2
    table = Table(rows, colWidths=widths)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, REF_GRID),
        ("BOX", (0, 0), (-1, -1), 0.8, REF_GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]
    for column in (1, 3):
        style.append(("BACKGROUND", (column, 0), (column, -1), REF_ROW_GREEN))
    table.setStyle(TableStyle(style))
    return table


def _manifest_footer_callback(styles: dict[str, ParagraphStyle], total: int):
    """تذييل التقرير: بيانات العنوان والهاتف والفاكس مع رقم الصفحة."""
    paragraphs = _footer_flowables(styles)

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        width, height = doc.pagesize
        inset = 10 * mm
        canvas.setStrokeColor(REF_GREEN)
        canvas.setLineWidth(0.8)
        canvas.rect(
            inset,
            inset,
            width - (2 * inset),
            height - (2 * inset),
            stroke=1,
            fill=0,
        )
        line_y = MARGIN_Y + MANIFEST_FOOTER_RESERVED - 8

        canvas.setStrokeColor(REF_GRID)
        canvas.setLineWidth(0.6)
        canvas.line(MANIFEST_MARGIN_X, line_y, width - MANIFEST_MARGIN_X, line_y)
        canvas.setStrokeColor(REF_GOLD)
        canvas.setLineWidth(2)
        canvas.line(
            width - MANIFEST_MARGIN_X - 70, line_y, width - MANIFEST_MARGIN_X, line_y
        )

        y = line_y - 5
        for paragraph in paragraphs:
            _, height = paragraph.wrapOn(canvas, MANIFEST_CONTENT_WIDTH, 1000)
            y -= height
            paragraph.drawOn(canvas, MANIFEST_MARGIN_X, y)

        page = Paragraph(
            rtl(f"صفحة {canvas.getPageNumber()} من {total}"),
            styles["footer_page"],
        )
        page_width, page_height = page.wrapOn(canvas, 120, 1000)
        page.drawOn(canvas, width - MANIFEST_MARGIN_X - page_width, y - page_height + 2)
        canvas.restoreState()

    return draw_footer


def build_manifest_pdf(
    *,
    campaign_name: str,
    driver_name: str,
    mobile_number: str,
    route_plan: str,
    bus_plate: str,
    supervisor: str,
    trip_date: object,
    operation_number: str,
    passengers: list[dict[str, str]],
) -> bytes:
    """يبني بيان الركاب بنموذج «كشف التفويج» المعتمد."""
    styles = _styles()

    trip_date_text = (
        trip_date.strftime("%d-%m-%Y")
        if isinstance(trip_date, date)
        else str(trip_date)
    )

    def make_flowables() -> list:
        count = len(passengers)
        compact = count > 4
        tight = count > 6
        flowables: list = _manifest_header(styles, operation_number)

        flowables.append(
            Paragraph(rtl("بيانات الرحلة"), styles["mf_section"])
        )
        flowables.append(Spacer(1, 3 if tight else 5 if compact else 8))
        nationality = next(
            (
                str(passenger.get("nationality") or "").strip()
                for passenger in passengers
                if passenger.get("nationality")
            ),
            "—",
        )
        fields = [
            ("اسم الحملة:", campaign_name),
            ("تاريخ الذهاب:", trip_date_text),
            ("مسار الرحلة (الخط):", route_plan),
            ("تشغيلة رقم:", operation_number),
            ("اسم السائق:", driver_name),
            ("رقم المركبة:", bus_plate),
            ("رقم الجوال:", mobile_number),
            ("المشرف:", supervisor),
            ("إجمالي عدد الركاب:", str(len(passengers))),
            ("الجنسية:", nationality),
        ]
        info_pad = 3 if tight else 4 if compact else 8
        flowables.append(_manifest_info_table(fields, styles, info_pad))
        flowables.append(Spacer(1, 10 if tight else 14 if compact else 24))

        flowables.append(
            Paragraph(rtl("بيانات أسماء الركاب"), styles["mf_section"])
        )
        flowables.append(Spacer(1, 4 if tight else 5 if compact else 10))

        # من اليسار إلى اليمين: الجنسية، الهوية، الاسم، م
        header_cells = [
            Paragraph(rtl("الجنسية"), styles["mf_table_head"]),
            Paragraph(rtl("رقم الهوية / الإقامة"), styles["mf_table_head"]),
            Paragraph(rtl("اسم الراكب"), styles["mf_table_head"]),
            Paragraph(rtl("م"), styles["mf_table_head"]),
        ]
        data: list[list[Paragraph]] = [header_cells]
        for index, passenger in enumerate(passengers, start=1):
            data.append(
                [
                    Paragraph(
                        rtl(_display_value(passenger.get("nationality"))),
                        styles["mf_table_cell"],
                    ),
                    Paragraph(
                        rtl(_display_value(passenger.get("id"))),
                        styles["mf_table_cell"],
                    ),
                    Paragraph(
                        rtl(_display_value(passenger.get("name"))),
                        styles["mf_table_cell"],
                    ),
                    Paragraph(str(index), styles["mf_index"]),
                ]
            )

        widths = [
            MANIFEST_CONTENT_WIDTH * 0.22,
            MANIFEST_CONTENT_WIDTH * 0.24,
            MANIFEST_CONTENT_WIDTH * 0.46,
            MANIFEST_CONTENT_WIDTH * 0.08,
        ]
        if count <= 3:
            row_pad = 34
        elif count <= 5:
            row_pad = 26
        elif count == 6:
            row_pad = 22
        elif count == 7:
            row_pad = 20
        elif count == 8:
            row_pad = 17
        elif count <= 10:
            row_pad = 14
        else:
            row_pad = 9

        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), REF_GREEN),
                    ("GRID", (0, 0), (-1, -1), 0.5, REF_GRID),
                    ("BOX", (0, 0), (-1, -1), 0.8, REF_GREEN),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [REF_ROW_GREEN, REF_ROW_BLUE],
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), row_pad),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), row_pad),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        flowables.append(table)
        return flowables

    def new_document(target: io.BytesIO) -> SimpleDocTemplate:
        return SimpleDocTemplate(
            target,
            pagesize=A4,
            leftMargin=MANIFEST_MARGIN_X,
            rightMargin=MANIFEST_MARGIN_X,
            topMargin=MARGIN_Y,
            bottomMargin=MARGIN_Y + MANIFEST_FOOTER_RESERVED,
            title="كشف تفويج ونقل ركاب",
            author=COMPANY_NAME_AR,
        )

    # بناء أوّل لحساب عدد الصفحات، ثم بناء نهائي بالتذييل الصحيح.
    counter_document = new_document(io.BytesIO())
    counter_document.build(make_flowables())

    buffer = io.BytesIO()
    document = new_document(buffer)
    footer = _manifest_footer_callback(styles, counter_document.page)
    document.build(make_flowables(), onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# التقرير الشامل
# ---------------------------------------------------------------------------
def build_comprehensive_report_pdf(
    *,
    start_date: object,
    end_date: object,
    type_filter: str | list[str] | None,
    groups: list[dict],
    total_cost: float,
    total_cost_excl: float | None = None,
    company: str | CompanyProfile | None = None,
) -> bytes:
    """يبني التقرير الشامل لصيانة الأسطول بهوية الشركة المختارة."""
    active = company_profile(company)
    styles = _styles()
    _, bold_font = register_fonts()
    total_excl = total_cost if total_cost_excl is None else total_cost_excl
    if isinstance(type_filter, (list, tuple, set)):
        filter_label = "، ".join(str(value).strip() for value in type_filter if str(value).strip())
        filter_label = filter_label or "كل الأنواع"
    else:
        filter_label = str(type_filter).strip() if type_filter else "كل الأنواع"

    flowables: list = _header(
        styles,
        title="",
        subtitle="ملخص المصروفات وأعمال الصيانة للمركبات والبنود المختارة",
        reference="",
        profile=active,
    )
    meta_fields = [
        ("فترة التقرير:", f"من {ltr(start_date)} إلى {ltr(end_date)}"),
        ("التصفية:", filter_label),
        ("تاريخ الإصدار:", f"{date.today():%d-%m-%Y}"),
    ]
    flowables.append(_content_section("معايير التقرير", styles))
    flowables.append(_info_table(meta_fields, styles, bold_font))
    flowables.append(Spacer(1, 12))

    records_count = sum(len(group.get("rows", [])) for group in groups)
    flowables.append(
        _summary_cards(
            [
                ("عدد المركبات / البنود", str(len(groups))),
                ("عدد سجلات الصيانة", str(records_count)),
                (
                    "إجمالي (بدون / شامل الضريبة)",
                    f"{total_excl:,.1f} / {total_cost:,.1f} ريال",
                ),
            ],
            styles,
        )
    )
    flowables.append(Spacer(1, 16))

    if not groups:
        empty_card = Table(
            [
                [
                    Paragraph(
                        rtl(
                            "لا توجد سجلات صيانة مطابقة لفترة التقرير "
                            "وخيارات التصفية المحددة."
                        ),
                        styles["empty"],
                    )
                ]
            ],
            colWidths=[CONTENT_WIDTH],
        )
        empty_card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), INFO_BG),
                    ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
                    ("LINEABOVE", (0, 0), (-1, 0), 3, ACCENT),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ]
            )
        )
        flowables.append(empty_card)
    else:
        # الترتيب المعروض من اليمين لليسار: الرقم، التاريخ، الورشة، نوع العمل،
        # بدون ضريبة، الضريبة، شامل الضريبة. والقائمة التالية من اليسار لليمين.
        headers = [
            "شامل الضريبة",
            "الضريبة",
            "بدون ضريبة",
            "نوع العمل",
            "الورشة",
            "التاريخ",
            "الرقم",
        ]
        widths = [
            CONTENT_WIDTH * 0.14,
            CONTENT_WIDTH * 0.14,
            CONTENT_WIDTH * 0.14,
            CONTENT_WIDTH * 0.21,
            CONTENT_WIDTH * 0.15,
            CONTENT_WIDTH * 0.12,
            CONTENT_WIDTH * 0.10,
        ]
        for index, group in enumerate(groups, start=1):
            bus_id = str(group.get("bus_id") or "—")
            vehicle_type = str(group.get("vehicle_type") or "مصروفات عامة")
            vehicle_user = str(group.get("vehicle_user") or "").strip()
            user_suffix = (
                f" - المستخدم: {vehicle_user}"
                if vehicle_user and vehicle_user != "—"
                else ""
            )
            title = _section_header(
                f"{index}. {vehicle_type} - رقم المركبة / البند : {bus_id}{user_suffix}",
                styles,
            )

            data: list[list[Paragraph]] = [
                [Paragraph(rtl(head), styles["table_head"]) for head in headers]
            ]
            for row in group.get("rows", []):
                cost_incl = float(row.get("cost_incl") or row.get("cost") or 0)
                cost_excl = float(row.get("cost_excl") or cost_incl)
                tax_value = max(cost_incl - cost_excl, 0.0)
                data.append(
                    [
                        Paragraph(
                            rtl(f"{cost_incl:,.1f} ريال"),
                            styles["table_cell"],
                        ),
                        Paragraph(
                            rtl(f"{tax_value:,.1f} ريال"), styles["table_cell"]
                        ),
                        Paragraph(
                            rtl(f"{cost_excl:,.1f} ريال"),
                            styles["table_cell"],
                        ),
                        Paragraph(
                            rtl(_display_value(row.get("job"))), styles["table_cell"]
                        ),
                        Paragraph(
                            rtl(_display_value(row.get("shop"))), styles["table_cell"]
                        ),
                        Paragraph(
                            rtl(_display_value(row.get("date"))), styles["table_cell"]
                        ),
                        Paragraph(
                            rtl(_display_value(row.get("bus_id"))),
                            styles["table_cell"],
                        ),
                    ]
                )

            table = _data_table(
                data, widths, header_background=PRIMARY_SOFT, row_padding=8
            )
            total_incl = float(
                group.get("total_incl") or group.get("total") or 0.0
            )
            total_excl_group = float(
                group.get("total_excl") or total_incl
            )
            total_box = Table(
                [
                    [
                        Paragraph(
                            rtl(
                                "إجمالي المركبة / البند رقم : "
                                f"{bus_id} ({vehicle_type}) — "
                                f"بدون ضريبة {total_excl_group:,.1f} / "
                                f"شامل الضريبة {total_incl:,.1f} ريال"
                            ),
                            styles["total"],
                        )
                    ]
                ],
                colWidths=[CONTENT_WIDTH],
            )
            total_box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
                        ("BOX", (0, 0), (-1, -1), 0.7, ACCENT),
                        ("LINEAFTER", (0, 0), (-1, -1), 3, ACCENT),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ]
                )
            )
            flowables.append(title)
            flowables.append(table)
            flowables.append(Spacer(1, 4))
            flowables.append(total_box)
            flowables.append(Spacer(1, 12))

        grand_total = Table(
            [
                [
                    Paragraph(
                        rtl(
                            "إجمالي الأسطول والبنود المختارة — "
                            f"بدون ضريبة {total_excl:,.1f} / "
                            f"شامل الضريبة {total_cost:,.1f} ريال"
                        ),
                        styles["grand_total"],
                    )
                ]
            ],
            colWidths=[CONTENT_WIDTH],
        )
        grand_total.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
                    ("BOX", (0, 0), (-1, -1), 0.8, ACCENT),
                    ("LINEABOVE", (0, 0), (-1, 0), 3, ACCENT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        flowables.append(Spacer(1, 4))
        flowables.append(grand_total)
        flowables.append(Spacer(1, 18))

        flowables.append(_content_section("اعتماد التقرير", styles))
        approval = Table(
            [
                [
                    Paragraph(rtl("اعتماد مدير الأسطول"), styles["signature"]),
                    Paragraph(rtl("أعدّ التقرير"), styles["signature"]),
                ],
                [
                    Paragraph(rtl("سيف المليكى"), styles["signature_name"]),
                    Paragraph(rtl("هيثم غريب"), styles["signature_name"]),
                ],
                ["", ""],
            ],
            colWidths=[CONTENT_WIDTH / 2] * 2,
            rowHeights=[26, 26, 42],
        )
        approval.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), INFO_BG),
                    ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                    ("LINEAFTER", (0, 0), (0, -1), 0.5, BORDER),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
                    ("LINEBELOW", (0, 2), (-1, 2), 0.9, MUTED),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        flowables.append(approval)

    return _build_document(
        flowables, "التقرير الشامل لصيانة الأسطول", styles, profile=active
    )
