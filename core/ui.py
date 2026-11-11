"""مكونات واجهة المستخدم المشتركة والهوية البصرية."""

from __future__ import annotations

import base64
import numbers
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from . import auth
from .config import (
    APP_VERSION,
    COMPANY_NAME,
    FALLBACK_LOGO_PATH,
    LOGO_CIRCLE_PATH,
    LOGO_PATH,
)
from .utils import (
    csv_bytes,
    esc,
    file_bytes,
    mime_for,
    resolve_stored_file,
    status_color,
)

_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');

    :root {
        --brog-primary: #0369a1;
        --brog-primary-dark: #1e3a8a;
        --brog-accent: #f59e0b;
        --brog-surface: #ffffff;
        --brog-border: #e2e8f0;
        --brog-muted: #64748b;
        --brog-text: #0f172a;
    }

    html, body, .stApp, [data-testid="stAppViewContainer"] {
        direction: rtl;
        text-align: right;
    }

    body, .stApp, [data-testid="stAppViewContainer"] {
        font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
    }

    [data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
    }

    [data-testid="stSidebar"] * {
        text-align: right;
    }

    [data-testid="stSidebarNav"] a {
        border-radius: 0.65rem;
        margin: 0.12rem 0.35rem;
    }

    [data-testid="stSidebarNav"] a p {
        font-weight: 600;
    }

    .brog-hero {
        display: flex;
        align-items: center;
        gap: 1rem;
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 55%, #1e3a8a 100%);
        color: #ffffff;
        padding: 1.35rem 1.6rem;
        border-radius: 1.1rem;
        border-bottom: 4px solid var(--brog-accent);
        box-shadow: 0 14px 30px rgba(2, 132, 199, 0.18);
        margin-bottom: 1.4rem;
    }

    .brog-hero__icon {
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 3.2rem;
        height: 3.2rem;
        border-radius: 1rem;
        background: rgba(255, 255, 255, 0.14);
        font-size: 1.6rem;
    }

    .brog-hero h1 {
        color: #ffffff;
        font-size: 1.55rem;
        font-weight: 800;
        margin: 0;
        line-height: 1.5;
    }

    .brog-hero p {
        color: #fef3c7;
        font-size: 0.95rem;
        font-weight: 600;
        margin: 0.25rem 0 0 0;
    }

    .brog-muted {
        color: var(--brog-muted);
        font-size: 0.9rem;
    }

    .brog-empty {
        border: 1.5px dashed #cbd5e1;
        border-radius: 1rem;
        background: #ffffff;
        padding: 1.5rem 1rem;
        text-align: center;
        color: var(--brog-muted);
        margin: 0.5rem 0 1rem 0;
    }

    .brog-empty__icon {
        font-size: 1.7rem;
        margin-bottom: 0.35rem;
    }

    .brog-record {
        background: #ffffff;
        border: 1px solid var(--brog-border);
        border-radius: 0.9rem;
        padding: 0.95rem 1.1rem;
        margin-bottom: 0.75rem;
    }

    .brog-record strong {
        color: var(--brog-primary-dark);
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid var(--brog-border);
        border-radius: 0.95rem;
        padding: 0.85rem 1rem;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
    }

    div[data-testid="stMetricLabel"] {
        color: #475569;
        font-weight: 700;
    }

    div[data-testid="stMetricValue"] {
        color: var(--brog-text);
    }

    [data-testid="stDataFrame"] {
        border-radius: 0.8rem;
        overflow: hidden;
    }

    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        border-radius: 0.65rem;
        font-weight: 700;
    }

    [data-testid="stFileUploader"] {
        direction: rtl;
        text-align: right;
    }

    [data-testid="stForm"] {
        background: #ffffff;
        border: 1px solid var(--brog-border);
        border-radius: 1rem;
        padding: 1.05rem;
    }

    input[type="number"] {
        direction: ltr;
        text-align: left;
    }

    /* ------------------------------------------------------------------
       لمسات الهوية البصرية: الخلفية، الشعار الدائري، البطاقات والأزرار
       ------------------------------------------------------------------ */
    .stApp {
        background:
            radial-gradient(circle at 100% 0%, rgba(3, 105, 161, 0.08), transparent 42%),
            radial-gradient(circle at 0% 100%, rgba(245, 158, 11, 0.07), transparent 38%),
            #f8fafc;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%);
        border-left: 1px solid var(--brog-border);
    }

    [data-testid="stSidebarLogo"] img,
    [data-testid="stSidebarLogo"] img.stLogo,
    [data-testid="stSidebarHeader"] img,
    [data-testid="stSidebarHeader"] img.stLogo {
        width: 68px !important;
        height: 68px !important;
        max-width: 68px !important;
        padding: 4px !important;
        box-sizing: border-box !important;
        border-radius: 50% !important;
        background: #ffffff !important;
        border: 2px solid rgba(3, 105, 161, 0.25) !important;
        box-shadow: 0 8px 20px rgba(3, 105, 161, 0.18) !important;
        object-fit: cover !important;
        display: block !important;
        margin: 0 auto !important;
    }

    [data-testid="stSidebarHeader"] {
        display: flex;
        justify-content: center;
        align-items: center;
        padding-bottom: 0.75rem;
    }

    [data-testid="stSidebarNavLink"] {
        transition: background 0.15s ease, color 0.15s ease;
    }

    [data-testid="stSidebarNavLink"]:hover {
        background: rgba(3, 105, 161, 0.07);
    }

    [data-testid="stSidebarNavLink"][aria-current="page"] {
        background: rgba(3, 105, 161, 0.12);
        box-shadow: inset -3px 0 0 var(--brog-primary);
    }

    [data-testid="stSidebarNavLink"][aria-current="page"] p,
    [data-testid="stSidebarNavLink"][aria-current="page"] span {
        color: var(--brog-primary);
        font-weight: 800;
    }

    .brog-hero {
        position: relative;
        overflow: hidden;
    }

    .brog-hero::after {
        content: "";
        position: absolute;
        inset: 0;
        background:
            radial-gradient(circle at 12% 20%, rgba(255, 255, 255, 0.18), transparent 32%),
            radial-gradient(circle at 88% 80%, rgba(245, 158, 11, 0.22), transparent 38%);
        pointer-events: none;
    }

    .brog-hero > * {
        position: relative;
        z-index: 1;
    }

    .brog-hero__icon {
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.28);
    }

    .brog-login-head {
        text-align: center;
        margin: 0.1rem 0 0.7rem 0;
    }

    .brog-login-logo {
        width: 88px;
        height: 88px;
        margin: 0 auto 0.6rem auto;
        padding: 4px;
        box-sizing: border-box;
        border-radius: 50%;
        background: #ffffff;
        border: 3px solid rgba(3, 105, 161, 0.22);
        box-shadow:
            0 16px 38px rgba(2, 132, 199, 0.20),
            0 0 0 6px rgba(255, 255, 255, 0.55);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    .brog-login-logo img {
        width: 100%;
        height: 100%;
        border-radius: 50%;
        object-fit: cover;
        display: block;
    }

    .brog-login-head h1 {
        color: var(--brog-primary);
        font-weight: 900;
        font-size: 1.45rem;
        letter-spacing: -0.2px;
        margin: 0 0 0.2rem 0;
    }

    .brog-login-head p {
        color: #b45309;
        font-weight: 700;
        font-size: 0.82rem;
        line-height: 1.6;
        margin: 0 auto;
        max-width: 440px;
    }

    /* ------------------------------------------------------------------
       شاشة تسجيل الدخول: كارت أنيق مع شريط علوي متدرج
       ------------------------------------------------------------------ */
    .st-key-login_shell {
        max-width: 460px;
        margin: 0 auto;
        animation: brog-login-in 0.45s ease-out both;
    }

    @keyframes brog-login-in {
        from {
            opacity: 0;
            transform: translateY(12px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .brog-login-cardhead {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        margin-bottom: 0.6rem;
    }

    .brog-login-badge {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2.5rem;
        height: 2.5rem;
        min-width: 2.5rem;
        border-radius: 0.8rem;
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
        color: #ffffff;
        font-size: 1.2rem;
        box-shadow: 0 10px 22px rgba(3, 105, 161, 0.25);
    }

    .brog-login-cardhead h2 {
        margin: 0;
        font-size: 1.05rem;
        font-weight: 800;
        color: var(--brog-primary-dark);
    }

    .brog-login-cardhead p {
        margin: 0.1rem 0 0 0;
        font-size: 0.78rem;
        color: var(--brog-muted);
    }

    .brog-login-card,
    .st-key-login_card {
        border-radius: 1.2rem !important;
        box-shadow: 0 24px 55px rgba(15, 23, 42, 0.12) !important;
        background: #ffffff;
        position: relative;
        overflow: hidden;
        padding: 1rem 1.15rem 1rem !important;
    }

    .st-key-login_card::before {
        content: "";
        position: absolute;
        top: 0;
        right: 0;
        left: 0;
        height: 5px;
        background: linear-gradient(90deg, #f59e0b 0%, #0284c7 42%, #0369a1 100%);
    }

    .st-key-login_card [data-testid="stForm"] {
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
        border-radius: 0 !important;
    }

    .st-key-login_card [data-testid="stWidgetLabel"] p {
        font-weight: 700;
        color: #334155;
        font-size: 0.86rem;
    }

    .st-key-login_card [data-testid="stForm"] [data-testid="stVerticalBlock"] {
        gap: 0.5rem;
    }

    .st-key-login_card [data-testid="stTextInputRootElement"] {
        min-height: 2.6rem;
        border-radius: 0.8rem !important;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        transition:
            border-color 0.15s ease,
            box-shadow 0.15s ease,
            background 0.15s ease;
    }

    .st-key-login_card [data-testid="stTextInputRootElement"]:focus-within {
        background: #ffffff;
        border-color: var(--brog-primary);
        box-shadow: 0 0 0 3px rgba(3, 105, 161, 0.14);
    }

    .st-key-login_card .stFormSubmitButton > button {
        min-height: 2.6rem;
        border-radius: 0.8rem;
        font-size: 0.98rem;
        letter-spacing: 0.2px;
    }

    .brog-login-hint {
        text-align: center;
        color: var(--brog-muted);
        font-size: 0.78rem;
        line-height: 1.6;
        margin-top: 0.45rem;
    }

    .brog-login-footer {
        text-align: center;
        color: #94a3b8;
        font-size: 0.76rem;
        line-height: 1.7;
        margin-top: 0.6rem;
    }

    .brog-login-footer strong {
        color: var(--brog-primary);
        font-weight: 800;
    }

    .brog-login-version {
        display: inline-block;
        margin-top: 0.3rem;
        padding: 0.1rem 0.6rem;
        border-radius: 999px;
        background: #e2e8f0;
        color: #475569;
        font-size: 0.7rem;
        font-weight: 700;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 1rem;
    }

    [data-testid="stExpander"] details {
        border-radius: 0.9rem;
        border-color: var(--brog-border);
        background: #ffffff;
    }

    [data-testid="stExpander"] summary {
        font-weight: 700;
    }

    div[data-testid="stMetric"] {
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 26px rgba(3, 105, 161, 0.10);
    }

    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 8px 18px rgba(3, 105, 161, 0.22);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 12px 24px rgba(3, 105, 161, 0.28);
    }

    [data-baseweb="input"] > div,
    [data-baseweb="select"] > div,
    [data-baseweb="textarea"] > div {
        border-radius: 0.65rem !important;
    }

    /* ------------------------------------------------------------------
       جدول HTML عادي: بيانات في منتصف الخلية وتلوين حسب حالة الصف
       ------------------------------------------------------------------ */
    .brog-table-wrap {
        width: 100%;
        overflow: auto;
        border: 1px solid var(--brog-border);
        border-radius: 0.95rem;
        background: #ffffff;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
        margin: 0.35rem 0 0.9rem 0;
    }

    table.brog-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.86rem;
        white-space: nowrap;
    }

    table.brog-table thead th {
        position: sticky;
        top: 0;
        z-index: 2;
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
        color: #ffffff;
        font-weight: 800;
        font-size: 0.82rem;
        text-align: center;
        vertical-align: middle;
        padding: 0.62rem 0.7rem;
        border: 1px solid rgba(255, 255, 255, 0.16);
        letter-spacing: 0.1px;
    }

    table.brog-table tbody td {
        text-align: center;
        vertical-align: middle;
        padding: 0.55rem 0.7rem;
        border-bottom: 1px solid #e2e8f0;
        border-left: 1px solid #eef2f7;
        color: #1e293b;
        font-weight: 600;
    }

    table.brog-table tbody tr:nth-child(even) td {
        background: #f8fafc;
    }

    table.brog-table tbody tr:hover td {
        background: rgba(2, 132, 199, 0.08);
    }

    table.brog-table tbody tr:last-child td {
        border-bottom: none;
    }

    /* ألوان الصفوف حسب حالة الصيانة */
    table.brog-table tbody tr.row-danger td {
        background: #fee2e2 !important;
        color: #7f1d1d !important;
        border-bottom-color: #fecaca;
    }

    table.brog-table tbody tr.row-warning td {
        background: #fef3c7 !important;
        color: #78350f !important;
        border-bottom-color: #fde68a;
    }

    table.brog-table tbody tr.row-ok td {
        background: #dcfce7 !important;
        color: #14532d !important;
        border-bottom-color: #bbf7d0;
    }

    table.brog-table tbody tr.row-muted td {
        background: #f1f5f9 !important;
        color: #475569 !important;
    }

    table.brog-table tbody tr.row-danger:hover td,
    table.brog-table tbody tr.row-warning:hover td,
    table.brog-table tbody tr.row-ok:hover td,
    table.brog-table tbody tr.row-muted:hover td {
        filter: brightness(0.97);
    }

    footer {
        visibility: hidden;
    }

    #MainMenu {
        visibility: hidden;
    }

    [data-testid="stAppDeployButton"] {
        display: none;
    }
</style>
"""


def inject_styles() -> None:
    """يحقن الهوية البصرية والاتجاه العربي مرة واحدة في بداية التطبيق."""
    st.html(_CSS)


def page_header(title: str, subtitle: str = "", icon: str = "🚌") -> None:
    subtitle_html = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    st.html(
        f"""
        <div class="brog-hero">
            <div class="brog-hero__icon">{esc(icon)}</div>
            <div>
                <h1>{esc(title)}</h1>
                {subtitle_html}
            </div>
        </div>
        """
    )


def section_title(title: str, subtitle: str = "") -> None:
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def empty_state(message: str, icon: str = "📭") -> None:
    st.html(
        f"""
        <div class="brog-empty">
            <div class="brog-empty__icon">{esc(icon)}</div>
            <div>{esc(message)}</div>
        </div>
        """
    )


def render_df(
    dataframe: pd.DataFrame | None,
    *,
    columns: list[str] | None = None,
    column_config: dict | None = None,
    height: int | None = None,
    alt: str = "جدول بيانات",
    empty_message: str = "لا توجد بيانات لعرضها.",
    row_style: Callable[[pd.Series], list[str]] | None = None,
) -> None:
    """يعرض إطار بيانات عربي الاتجاه مع حالة فارغة واضحة.

    يمكن تمرير ``row_style`` لتلوين كل صف حسب حالته، مثل تلوين صفوف
    الأسطول حسب حالة الصيانة.
    """
    if dataframe is None or dataframe.empty:
        empty_state(empty_message)
        return

    view: object = dataframe[columns] if columns else dataframe
    if row_style is not None:
        view = view.style.apply(row_style, axis=1)
    options: dict[str, object] = {
        "width": "stretch",
        "hide_index": True,
        "alt": alt,
    }
    if height:
        options["height"] = height
    if column_config:
        options["column_config"] = column_config
    st.dataframe(view, **options)


def _cell_text(value: object) -> str:
    """يهيّئ قيمة الخلية للعرض داخل جدول HTML."""
    if value is None:
        return "—"
    if isinstance(value, str):
        return value.strip() or "—"

    try:
        if bool(pd.isna(value)):
            return "—"
    except (TypeError, ValueError):
        pass

    if isinstance(value, numbers.Integral):
        return f"{int(value):,}"
    if isinstance(value, numbers.Real):
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}"

    text = str(value).strip()
    return text if text else "—"


def html_table(
    dataframe: pd.DataFrame | None,
    *,
    columns: list[str] | None = None,
    headers: dict[str, str] | None = None,
    row_class: Callable[[pd.Series], str] | None = None,
    empty_message: str = "لا توجد بيانات لعرضها.",
    max_height: str | None = None,
) -> None:
    """يعرض جدولاً عادياً بتنسيق جميل مع توسيط البيانات في الخلايا.

    ``headers`` يتيح إعادة تسمية الأعمدة للعرض، و``row_class`` يعيد اسم
    صنف CSS لكل صف (مثل ``row-danger``) لتلوين الصف حسب حالته.
    """
    if dataframe is None or dataframe.empty:
        empty_state(empty_message)
        return

    view = dataframe[columns] if columns else dataframe
    labels = headers or {}
    head_cells = "".join(
        f"<th>{esc(labels.get(str(col), str(col)))}</th>" for col in view.columns
    )

    body_rows: list[str] = []
    for _, row in view.iterrows():
        css_class = row_class(row) if row_class is not None else ""
        class_attr = f' class="{esc(css_class)}"' if css_class else ""
        cells = "".join(
            f"<td>{esc(_cell_text(row[col]))}</td>" for col in view.columns
        )
        body_rows.append(f"<tr{class_attr}>{cells}</tr>")

    wrap_style = f' style="max-height:{esc(max_height)}"' if max_height else ""
    st.html(
        f"""
        <div class="brog-table-wrap"{wrap_style}>
            <table class="brog-table">
                <thead><tr>{head_cells}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """
    )


def status_badge(status: str) -> None:
    st.badge(status, color=status_color(status))


def download_file_button(
    stored_path: object,
    label: str = "⬇️ تحميل الملف المرفق",
    *,
    key: str,
    mime: str | None = None,
) -> None:
    """يعرض زر تحميل فقط عند وجود ملف فعلي على القرص."""
    data = file_bytes(stored_path)
    path = resolve_stored_file(stored_path)

    if data is None or path is None:
        st.caption("لا يوجد ملف مرفق.")
        return

    st.download_button(
        label,
        data=data,
        file_name=path.name,
        mime=mime or mime_for(path),
        key=key,
        width="stretch",
    )


def csv_download_button(
    dataframe: pd.DataFrame,
    filename: str,
    label: str = "⬇️ تصدير البيانات (CSV)",
    *,
    key: str,
) -> None:
    if dataframe is None or dataframe.empty:
        return
    st.download_button(
        label,
        data=csv_bytes(dataframe),
        file_name=filename,
        mime="text/csv",
        key=key,
        width="stretch",
    )


def logo_path() -> Path | None:
    """يعيد أفضل شعار متاح، مع تفضيل النسخة الدائرية الشفافة."""
    if LOGO_CIRCLE_PATH.is_file():
        return LOGO_CIRCLE_PATH
    if LOGO_PATH.is_file():
        return LOGO_PATH
    if FALLBACK_LOGO_PATH.is_file():
        return FALLBACK_LOGO_PATH
    return None


def logo_data_uri() -> str:
    path = logo_path()
    if path is None:
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def sidebar_user_panel() -> None:
    """يعرض بيانات المستخدم الحالي وإجراءات الجلسة في الشريط الجانبي."""
    user = auth.current_user()

    with st.sidebar:
        st.markdown(f"**{esc(user['full_name'])}**")
        st.caption(f"اسم المستخدم: {esc(user['username'])}")
        st.badge(
            str(user["role_label"]),
            color="green" if user["is_admin"] else "blue",
        )
        st.divider()

        with st.expander("تغيير كلمة المرور"):
            with st.form("sidebar_change_password", clear_on_submit=True):
                old_password = st.text_input(
                    "كلمة المرور الحالية", type="password"
                )
                new_password = st.text_input(
                    "كلمة المرور الجديدة", type="password"
                )
                confirm_password = st.text_input(
                    "تأكيد كلمة المرور الجديدة", type="password"
                )
                submitted = st.form_submit_button(
                    "حفظ كلمة المرور",
                    type="primary",
                    width="stretch",
                )

            if submitted:
                success, message = auth.change_password(
                    old_password, new_password, confirm_password
                )
                if success:
                    st.success(message)
                else:
                    st.error(message)

        if st.button(
            "تسجيل الخروج",
            icon=":material/logout:",
            width="stretch",
        ):
            auth.logout()
            st.rerun()

        st.divider()
        st.caption(f"{COMPANY_NAME} • الإصدار {APP_VERSION}")
