"""نقطة تشغيل نظام إدارة الأسطول.

تسجيل الدخول، بناء قائمة الصفحات، ثم تشغيل الصفحة المختارة.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import auth, db, ui
from core.config import APP_TITLE, APP_VERSION, COMPANY_NAME, COMPANY_SUBTITLE

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    db.init_db()
except Exception as error:  # pragma: no cover - حماية من أعطال التهيئة
    st.error(f"تعذر تهيئة قاعدة البيانات: {error}")
    st.stop()

ui.inject_styles()


# ---------------------------------------------------------------------------
# شاشة تسجيل الدخول
# ---------------------------------------------------------------------------
_LOGIN_PAGE_CSS = """
<style>
    /* إخفاء الشريط الجانبي والهيدر في شاشة الدخول فقط */
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"],
    header[data-testid="stHeader"] {
        display: none !important;
    }

    /* تمركز عمودي كامل لمحتوى الدخول */
    [data-testid="stMainBlockContainer"] {
        min-height: 100vh;
        min-height: 100dvh;
        display: flex;
        flex-direction: column;
        justify-content: center;
        justify-content: safe center;
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }

    /* خلفية أعمق وأكثر دفئاً لشاشة الدخول */
    .stApp {
        background:
            radial-gradient(circle at 15% 15%, rgba(2, 132, 199, 0.10), transparent 40%),
            radial-gradient(circle at 85% 85%, rgba(245, 158, 11, 0.10), transparent 38%),
            linear-gradient(180deg, #f8fafc 0%, #eef4fa 100%);
    }
</style>
"""


def render_login() -> None:
    st.html(_LOGIN_PAGE_CSS)

    with st.container(key="login_shell"):
        flash_message = st.session_state.pop("flash_message", None)
        if flash_message:
            st.success(flash_message)

        logo_uri = ui.logo_data_uri()
        logo_html = (
            f'<div class="brog-login-logo">'
            f'<img src="{logo_uri}" alt="شعار الشركة"></div>'
            if logo_uri
            else '<div class="brog-login-logo"><span style="font-size:2.6rem;">🚌</span></div>'
        )

        st.html(
            f"""
            <div class="brog-login-head">
                {logo_html}
                <h1>{COMPANY_NAME}</h1>
                <p>{COMPANY_SUBTITLE}</p>
            </div>
            """
        )

        with st.container(border=True, key="login_card"):
            st.html(
                """
                <div class="brog-login-cardhead">
                    <div class="brog-login-badge">🔐</div>
                    <div>
                        <h2>تسجيل الدخول</h2>
                        <p>الدخول مخصص للموظفين المصرح لهم فقط.</p>
                    </div>
                </div>
                """
            )

            with st.form("login_form"):
                username = st.text_input(
                    "اسم المستخدم",
                    placeholder="أدخل اسم المستخدم",
                    icon=":material/person:",
                    autocomplete="username",
                )
                password = st.text_input(
                    "كلمة المرور",
                    type="password",
                    placeholder="أدخل كلمة المرور",
                    icon=":material/lock:",
                    autocomplete="current-password",
                )
                submitted = st.form_submit_button(
                    "دخول إلى النظام",
                    type="primary",
                    width="stretch",
                    icon=":material/login:",
                )

            if submitted:
                if not (username or "").strip() or not (password or ""):
                    st.warning("يرجى إدخال اسم المستخدم وكلمة المرور.")
                else:
                    success, message = auth.login(username, password)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

            st.html(
                '<div class="brog-login-hint">'
                "نسيت كلمة المرور؟ تواصل مع مدير النظام لإعادة تعيينها."
                "</div>"
            )

        st.html(
            f"""
            <div class="brog-login-footer">
                <strong>{COMPANY_NAME}</strong><br>
                جميع الحقوق محفوظة © {datetime.now().year}
                <div class="brog-login-version">الإصدار {APP_VERSION}</div>
            </div>
            """
        )


auth.init_state()

if not st.session_state.get("logged_in"):
    render_login()
    st.stop()

if auth.is_session_expired():
    auth.logout()
    st.warning("انتهت مدة الجلسة لأسباب أمنية. يرجى تسجيل الدخول مرة أخرى.")
    st.stop()

st.session_state["last_activity"] = datetime.now()


# ---------------------------------------------------------------------------
# بناء قائمة الصفحات
# ---------------------------------------------------------------------------
def build_navigation():
    pages: dict[str, list[st.Page]] = {
        "الرئيسية": [
            st.Page(
                "app_pages/dashboard.py",
                title="لوحة التحكم",
                icon=":material/home:",
                default=True,
            ),
        ],
        "الأسطول": [
            st.Page(
                "app_pages/vehicles.py",
                title="إدارة المركبات",
                icon=":material/directions_bus:",
            ),
            st.Page(
                "app_pages/vehicle_types.py",
                title="أنواع المركبات",
                icon=":material/category:",
            ),
        ],
        "الصيانة": [
            st.Page(
                "app_pages/maintenance_logs.py",
                title="سجلات الصيانة",
                icon=":material/build:",
            ),
            st.Page(
                "app_pages/inspections.py",
                title="الفحص الدوري",
                icon=":material/fact_check:",
            ),
            st.Page(
                "app_pages/workshops.py",
                title="الورش والمراكز",
                icon=":material/garage:",
            ),
            st.Page(
                "app_pages/maintenance_types.py",
                title="أنواع الصيانة",
                icon=":material/handyman:",
            ),
        ],
        "الطاقة": [
            st.Page(
                "app_pages/batteries.py",
                title="البطاريات والضمان",
                icon=":material/battery_charging_full:",
            ),
        ],
        "العقود والمواقف": [
            st.Page(
                "app_pages/hotels.py",
                title="الفنادق والعقود",
                icon=":material/hotel:",
            ),
            st.Page(
                "app_pages/parking.py",
                title="المواقف الذكية",
                icon=":material/local_parking:",
            ),
        ],
        "التقارير": [
            st.Page(
                "app_pages/reports.py",
                title="التقرير الشامل",
                icon=":material/bar_chart:",
            ),
            st.Page(
                "app_pages/manifest.py",
                title="بيان الركاب",
                icon=":material/groups:",
            ),
        ],
    }

    # جميع الصفحات متاحة لكل المستخدمين المسجلين، بما فيها الإدارة والنسخ الاحتياطي.
    pages["الإدارة"] = [
        st.Page(
            "app_pages/users.py",
            title="المستخدمون والصلاحيات",
            icon=":material/manage_accounts:",
        ),
        st.Page(
            "app_pages/backup.py",
            title="النسخ الاحتياطي",
            icon=":material/backup:",
        ),
    ]

    return pages


logo = ui.logo_path()
if logo is not None:
    st.logo(str(logo), size="large")

navigation = st.navigation(build_navigation(), position="sidebar")
ui.sidebar_user_panel()
navigation.run()