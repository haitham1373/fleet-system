"""توليد تقارير PDF عربية جاهزة للطباعة والتنزيل.

يعتمد على ReportLab مع دعم تشكيل الحروف العربية واتجاه النص من اليمين
إلى اليسار عبر ``arabic_reshaper`` و``python-bidi``، ويستخدم خط Tahoma
عند توفره (لأنه الأقرب لتصميم التقارير الرسمية) مع الرجوع إلى خط Amiri
المرفق مع المشروع.
"""

from __future__ import annotations

import io
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

PRIMARY = colors.HexColor("#0369a1")
PRIMARY_LIGHT = colors.HexColor("#0284c7")
DARK = colors.HexColor("#0f172a")
TEXT = colors.HexColor("#334155")
MUTED = colors.HexColor("#475569")
BORDER = colors.HexColor("#cbd5e1")
INFO_BG = colors.HexColor("#e2e8f0")

COMPANY_NAME_AR = "شركة بروج العالم للنقل"
COMPANY_NAME_AR_LINE2 = "البري"
COMPANY_NAME_EN = "Burooj Al-Alam Land Transport"
COMPANY_NAME_EN_LINE2 = "Company"
FOOTER_AR = (
    "( سنترال ) مكة المكرمة – بطحاء قريش – الشارع العام – تلفون : "
    "\u202a+966 2 5771177\u202c – فاكس : \u202a+966 2 5729455\u202c – ص.ب : 5941"
)
FOOTER_EN = (
    "Makkah Al-Mukaramah – main road – Bathaa Quraish – Tel : "
    "+966 2 5771177 – Fax : +966 2 5729455 – P.O.Box : 5941"
)
FOOTER_EMAIL = "broujalalam@hotmail.com"

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
        [windows_fonts / "tahoma.ttf", BASE_DIR / "Amiri-Regular.ttf"]
    )
    bold = _first_existing(
        [
            windows_fonts / "tahomabd.ttf",
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


def _field_markup(label: str, value: object, bold_font: str) -> str:
    """ينشئ نص الحقل بعنوان عريض وقيمة عادية مع الحفاظ على ترتيب الأرقام."""
    label_visual = rtl(label)
    value_visual = rtl(value)
    bold_label = f'<font name="{bold_font}">{xml_escape(label_visual)}</font>'
    if value_visual:
        return f"{xml_escape(value_visual)} {bold_label}"
    return bold_label


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
            leading=19,
            alignment=TA_CENTER,
            textColor=PRIMARY,
        ),
        "brand_en": ParagraphStyle(
            "brand_en",
            fontName=bold_font,
            fontSize=9.5,
            leading=14,
            alignment=TA_CENTER,
            textColor=PRIMARY,
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
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            fontName=body_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=DARK,
        ),
        "section_title": ParagraphStyle(
            "section_title",
            fontName=bold_font,
            fontSize=11,
            leading=15,
            alignment=TA_RIGHT,
            textColor=PRIMARY,
            keepWithNext=True,
        ),
        "total": ParagraphStyle(
            "total",
            fontName=bold_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=DARK,
        ),
        "grand_total": ParagraphStyle(
            "grand_total",
            fontName=bold_font,
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            textColor=DARK,
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
        "empty": ParagraphStyle(
            "empty",
            fontName=body_font,
            fontSize=10,
            leading=16,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
    }


# ---------------------------------------------------------------------------
# مكوّنات مشتركة
# ---------------------------------------------------------------------------
def _logo_path() -> Path | None:
    for candidate in (LOGO_CIRCLE_PATH, LOGO_PATH):
        if candidate.is_file():
            return candidate
    return None


def _header(styles: dict[str, ParagraphStyle]) -> list:
    arabic = Paragraph(
        f"{rtl(COMPANY_NAME_AR)}<br/>{rtl(COMPANY_NAME_AR_LINE2)}",
        styles["brand_ar"],
    )
    english = Paragraph(
        f"{COMPANY_NAME_EN}<br/>{COMPANY_NAME_EN_LINE2}",
        styles["brand_en"],
    )

    logo: object = ""
    path = _logo_path()
    if path is not None:
        image = Image(str(path))
        image.drawWidth = 71
        image.drawHeight = 71
        logo = image

    header = Table(
        [[english, logo, arabic]],
        colWidths=[CONTENT_WIDTH * 0.36, CONTENT_WIDTH * 0.28, CONTENT_WIDTH * 0.36],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # توسيط الشعار داخل خليته الوسطى ليطابق التصميم المرجعي
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    rule = HRFlowable(
        width="100%",
        thickness=2,
        color=PRIMARY,
        spaceBefore=7,
        spaceAfter=9,
    )
    return [header, rule]


FOOTER_RESERVED = 46  # المساحة المحجوزة أسفل كل صفحة للتذييل (بالنقاط)


def _footer_flowables(styles: dict[str, ParagraphStyle]) -> list[Paragraph]:
    """فقرات تذييل التقرير (بيانات الشركة) التي تُرسم أسفل كل صفحة."""
    return [
        Paragraph(rtl(FOOTER_AR), styles["footer_ar"]),
        Paragraph(FOOTER_EN, styles["footer_en"]),
        Paragraph(FOOTER_EMAIL, styles["footer_en"]),
    ]


def _frame_canvas(canvas, doc) -> None:
    """يرسم إطاراً أنيقاً مزدوجاً (بزوايا دائرية) حول صفحة التقرير."""
    width, height = doc.pagesize
    canvas.saveState()

    # الإطار الخارجي: خط سميك بلون الهوية
    outer = 7 * mm
    canvas.setStrokeColor(PRIMARY)
    canvas.setLineWidth(1.4)
    canvas.roundRect(
        outer,
        outer,
        width - 2 * outer,
        height - 2 * outer,
        7 * mm,
        stroke=1,
        fill=0,
    )

    # الإطار الداخلي: خط رفيع أفتح لإعطاء عمق وجمال
    inner = 9.5 * mm
    canvas.setStrokeColor(PRIMARY_LIGHT)
    canvas.setLineWidth(0.6)
    canvas.roundRect(
        inner,
        inner,
        width - 2 * inner,
        height - 2 * inner,
        5 * mm,
        stroke=1,
        fill=0,
    )

    canvas.restoreState()


def _footer_callback(styles: dict[str, ParagraphStyle]):
    """ينشئ دالة ترسم تذييل الشركة مثبتاً أسفل كل صفحة."""
    paragraphs = _footer_flowables(styles)

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        width, _ = doc.pagesize
        line_y = MARGIN_Y + FOOTER_RESERVED - 8
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_X, line_y, width - MARGIN_X, line_y)

        y = line_y - 4
        for paragraph in paragraphs:
            _, height = paragraph.wrapOn(canvas, CONTENT_WIDTH, 1000)
            y -= height
            paragraph.drawOn(canvas, MARGIN_X, y)
        canvas.restoreState()

    return draw_footer


def _info_table(
    fields: list[tuple[str, object]],
    styles: dict[str, ParagraphStyle],
    bold_font: str,
) -> Table:
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
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), INFO_BG),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _build_document(
    flowables: list,
    title: str,
    styles: dict[str, ParagraphStyle],
) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_Y,
        bottomMargin=MARGIN_Y + FOOTER_RESERVED,
        title=title,
        author=COMPANY_NAME_AR,
    )
    footer = _footer_callback(styles)

    def decorate_page(canvas, doc) -> None:
        """يرسم إطار الصفحة ثم التذييل في كل صفحة."""
        _frame_canvas(canvas, doc)
        footer(canvas, doc)

    document.build(flowables, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# بيان الركاب
# ---------------------------------------------------------------------------
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
    """يبني بيان الركاب بصيغة PDF مطابق لتصميم الشركة الرسمي."""
    styles = _styles()
    body_font, bold_font = register_fonts()

    trip_date_text = (
        trip_date.strftime("%d-%m-%Y")
        if isinstance(trip_date, date)
        else str(trip_date)
    )

    fields = [
        ("اسم الحملة:", campaign_name),
        ("اسم السائق:", driver_name),
        ("رقم الجوال:", mobile_number),
        ("الخطة:", route_plan),
        ("رقم اللوحة:", bus_plate),
        ("المشرف:", supervisor),
        ("تاريخ الذهاب:", trip_date_text),
        ("تشغيلة رقم:", operation_number),
        ("عدد الركاب:", str(len(passengers))),
    ]

    flowables: list = _header(styles)
    flowables.append(_info_table(fields, styles, bold_font))
    flowables.append(Spacer(1, 12))

    # الأعمدة بترتيب العرض من اليسار إلى اليمين: الجنسية، الهوية، الاسم، م
    header_cells = [
        Paragraph(rtl("الجنسية"), styles["table_head"]),
        Paragraph(rtl("رقم الهوية / الإقامة"), styles["table_head"]),
        Paragraph(rtl("اسم الراكب"), styles["table_head"]),
        Paragraph(rtl("م"), styles["table_head"]),
    ]
    data: list[list[Paragraph]] = [header_cells]
    for index, passenger in enumerate(passengers, start=1):
        data.append(
            [
                Paragraph(rtl(passenger.get("nationality", "")), styles["table_cell"]),
                Paragraph(rtl(passenger.get("id", "")), styles["table_cell"]),
                Paragraph(rtl(passenger.get("name", "")), styles["table_cell"]),
                Paragraph(str(index), styles["table_cell"]),
            ]
        )

    widths = [
        CONTENT_WIDTH * 0.15,
        CONTENT_WIDTH * 0.30,
        CONTENT_WIDTH * 0.45,
        CONTENT_WIDTH * 0.10,
    ]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.6, BORDER),
                ("BOX", (0, 0), (-1, -1), 0.8, PRIMARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    flowables.append(table)

    return _build_document(flowables, "بيان الركاب", styles)


# ---------------------------------------------------------------------------
# التقرير الشامل
# ---------------------------------------------------------------------------
def build_comprehensive_report_pdf(
    *,
    start_date: object,
    end_date: object,
    type_filter: str,
    groups: list[dict],
    total_cost: float,
) -> bytes:
    """يبني التقرير الشامل لصيانة الأسطول بصيغة PDF."""
    styles = _styles()
    body_font, bold_font = register_fonts()

    flowables: list = _header(styles)
    meta_fields = [
        ("فترة التقرير:", f"من {ltr(start_date)} إلى {ltr(end_date)}"),
        ("التصفية:", type_filter),
    ]
    flowables.append(_info_table(meta_fields, styles, bold_font))
    flowables.append(Spacer(1, 12))

    if not groups:
        flowables.append(
            Paragraph(
                rtl("لا توجد سجلات صيانة مطابقة لفترة التقرير وخيارات التصفية المحددة."),
                styles["empty"],
            )
        )
    else:
        # ترتيب الأعمدة من اليسار إلى اليمين ليطابق العرض العربي.
        headers = ["الرقم", "التاريخ", "نوع العمل", "التكلفة", "الورشة", "الحالة"]
        widths = [
            CONTENT_WIDTH * 0.14,
            CONTENT_WIDTH * 0.16,
            CONTENT_WIDTH * 0.24,
            CONTENT_WIDTH * 0.14,
            CONTENT_WIDTH * 0.18,
            CONTENT_WIDTH * 0.14,
        ]
        for group in groups:
            bus_id = str(group.get("bus_id") or "—")
            vehicle_type = str(group.get("vehicle_type") or "مصروفات عامة")
            title = Paragraph(
                rtl(f"{vehicle_type} - رقم المركبة / البند : {bus_id}"),
                styles["section_title"],
            )

            data: list[list[Paragraph]] = [
                [Paragraph(rtl(head), styles["table_head"]) for head in headers]
            ]
            for row in group.get("rows", []):
                data.append(
                    [
                        Paragraph(rtl(row.get("bus_id", "")), styles["table_cell"]),
                        Paragraph(rtl(row.get("date", "")), styles["table_cell"]),
                        Paragraph(rtl(row.get("job", "")), styles["table_cell"]),
                        Paragraph(
                            rtl(f"{float(row.get('cost') or 0):,.1f} ريال"),
                            styles["table_cell"],
                        ),
                        Paragraph(rtl(row.get("shop", "")), styles["table_cell"]),
                        Paragraph(rtl(row.get("status", "")), styles["table_cell"]),
                    ]
                )

            table = Table(data, colWidths=widths, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_LIGHT),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            total = float(group.get("total") or 0.0)
            total_box = Table(
                [
                    [
                        Paragraph(
                            rtl(
                                "إجمالي تكلفة المركبة / البند رقم : "
                                f"{bus_id} ({vehicle_type}) : {total:,.1f} ريال"
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
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                        ("BOX", (0, 0), (-1, -1), 0.8, PRIMARY_LIGHT),
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
            flowables.append(total_box)
            flowables.append(Spacer(1, 8))

        grand_total = Table(
            [
                [
                    Paragraph(
                        rtl(
                            "إجمالي التكلفة الكلية للأسطول والبنود المختارة: "
                            f"{total_cost:,.1f} ريال"
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
                    ("BACKGROUND", (0, 0), (-1, -1), INFO_BG),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        flowables.append(Spacer(1, 6))
        flowables.append(grand_total)

    return _build_document(flowables, "التقرير الشامل لصيانة الأسطول", styles)
