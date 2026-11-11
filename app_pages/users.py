"""المستخدمون والصلاحيات: إدارة الحسابات والأدوار (مدير النظام فقط)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import streamlit as st

from core import auth, db, ui
from core.security import hash_password, validate_password
from core.utils import clean_text

auth.require_admin()
ui.page_header(
    "المستخدمون والصلاحيات",
    "إدارة حسابات الدخول وأدوار المدير والمستخدم العادي",
    "👥",
)

ROLE_OPTIONS = {
    "مدير النظام": auth.ROLE_ADMIN,
    "مستخدم": auth.ROLE_USER,
}
ROLE_LABELS = {value: label for label, value in ROLE_OPTIONS.items()}

users = db.read_df(
    """
    SELECT ID, Username, FullName, Role, IsActive, CreatedAt, LastLoginAt
      FROM Users
     ORDER BY Username
    """
)

if not users.empty:
    users["الدور"] = users["Role"].map(ROLE_LABELS).fillna("مستخدم")
    users["الحالة"] = users["IsActive"].apply(
        lambda value: "نشط" if int(value or 0) else "موقوف"
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric("إجمالي المستخدمين", f"{len(users):,}")
    metric_columns[1].metric(
        "مديرو النظام",
        f"{int((users['Role'] == auth.ROLE_ADMIN).sum()):,}",
    )
    metric_columns[2].metric(
        "حسابات نشطة",
        f"{int((users['IsActive'].fillna(0).astype(int) == 1).sum()):,}",
    )
    metric_columns[3].metric(
        "حسابات موقوفة",
        f"{int((users['IsActive'].fillna(0).astype(int) == 0).sum()):,}",
    )
    st.write("")

# ---------------------------------------------------------------------------
# إضافة مستخدم
# ---------------------------------------------------------------------------
with st.expander("➕ إضافة مستخدم جديد"):
    with st.form("add_user_form", clear_on_submit=True):
        first, second = st.columns(2)
        with first:
            username = st.text_input(
                "اسم المستخدم *",
                placeholder="مثال: ahmed",
            )
            full_name = st.text_input(
                "الاسم الكامل",
                placeholder="اسم الموظف",
            )
        with second:
            role_label = st.selectbox("الدور", list(ROLE_OPTIONS))
            password = st.text_input("كلمة المرور *", type="password")
            confirm_password = st.text_input(
                "تأكيد كلمة المرور *",
                type="password",
            )

        submitted = st.form_submit_button(
            "حفظ المستخدم",
            type="primary",
            width="stretch",
        )

    if submitted:
        username_clean = clean_text(username, 80)
        full_name_clean = clean_text(full_name, 120) or username_clean
        password_error = validate_password(password)

        if not username_clean:
            st.error("يرجى إدخال اسم المستخدم.")
        elif " " in username_clean:
            st.error("اسم المستخدم لا يمكن أن يحتوي على مسافات.")
        elif password != confirm_password:
            st.error("كلمة المرور وتأكيدها غير متطابقين.")
        elif password_error:
            st.error(password_error)
        elif db.fetch_one(
            "SELECT 1 FROM Users WHERE LOWER(Username)=LOWER(?)",
            (username_clean,),
        ):
            st.error("اسم المستخدم مستخدم مسبقاً.")
        else:
            try:
                db.execute(
                    """
                    INSERT INTO Users
                        (Username, Password, FullName, Role, IsActive, CreatedAt)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (
                        username_clean,
                        hash_password(password),
                        full_name_clean,
                        ROLE_OPTIONS[role_label],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "المستخدمون",
                    username_clean,
                    f"الدور: {role_label}",
                )
                st.success("تمت إضافة المستخدم بنجاح.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("اسم المستخدم مستخدم مسبقاً.")
            except Exception as error:
                st.error(f"تعذر حفظ المستخدم: {error}")

# ---------------------------------------------------------------------------
# تعديل مستخدم
# ---------------------------------------------------------------------------
if not users.empty:
    with st.expander("⚙️ تعديل حساب مستخدم"):
        usernames = users["Username"].astype(str).tolist()
        selected_username = st.selectbox(
            "اختر المستخدم",
            usernames,
            key="manage_user",
        )
        selected_user = db.fetch_one(
            "SELECT * FROM Users WHERE Username=?",
            (selected_username,),
        )

        if selected_user:
            current_role = str(selected_user.get("Role") or auth.ROLE_USER)
            role_index = (
                list(ROLE_OPTIONS.values()).index(current_role)
                if current_role in ROLE_OPTIONS.values()
                else 1
            )

            with st.form("edit_user_form"):
                first, second = st.columns(2)
                with first:
                    st.text_input(
                        "اسم المستخدم",
                        value=selected_username,
                        disabled=True,
                    )
                    new_full_name = st.text_input(
                        "الاسم الكامل",
                        value=str(selected_user.get("FullName") or ""),
                    )
                with second:
                    new_role_label = st.selectbox(
                        "الدور",
                        list(ROLE_OPTIONS),
                        index=role_index,
                    )
                    is_active = st.checkbox(
                        "الحساب نشط",
                        value=bool(int(selected_user.get("IsActive") or 0)),
                    )

                st.markdown("##### إعادة تعيين كلمة المرور (اختياري)")
                password_first, password_second = st.columns(2)
                with password_first:
                    new_password = st.text_input(
                        "كلمة المرور الجديدة",
                        type="password",
                    )
                with password_second:
                    confirm_new_password = st.text_input(
                        "تأكيد كلمة المرور الجديدة",
                        type="password",
                    )

                save_changes = st.form_submit_button(
                    "حفظ التعديلات",
                    type="primary",
                    width="stretch",
                )

            if save_changes:
                new_role = ROLE_OPTIONS[new_role_label]
                active_admins = int(
                    db.scalar(
                        "SELECT COUNT(*) FROM Users "
                        "WHERE Role='admin' AND IsActive=1",
                        default=0,
                    )
                    or 0
                )
                removing_admin = (
                    current_role == auth.ROLE_ADMIN
                    and int(selected_user.get("IsActive") or 0) == 1
                    and (new_role != auth.ROLE_ADMIN or not is_active)
                )
                password_error = (
                    validate_password(new_password) if new_password else None
                )

                if selected_username == auth.current_username() and not is_active:
                    st.error("لا يمكنك إيقاف حسابك الحالي.")
                elif (
                    selected_username == auth.current_username()
                    and new_role != auth.ROLE_ADMIN
                ):
                    st.error("لا يمكنك إزالة صلاحية المدير عن حسابك الحالي.")
                elif removing_admin and active_admins <= 1:
                    st.error("يجب أن يبقى مدير نظام نشط واحد على الأقل.")
                elif new_password and new_password != confirm_new_password:
                    st.error("كلمة المرور الجديدة وتأكيدها غير متطابقين.")
                elif password_error:
                    st.error(password_error)
                else:
                    try:
                        with db.get_conn() as connection:
                            connection.execute(
                                """
                                UPDATE Users
                                   SET FullName=?, Role=?, IsActive=?
                                 WHERE Username=?
                                """,
                                (
                                    clean_text(new_full_name, 120)
                                    or selected_username,
                                    new_role,
                                    int(is_active),
                                    selected_username,
                                ),
                            )
                            if new_password:
                                connection.execute(
                                    "UPDATE Users SET Password=? WHERE Username=?",
                                    (hash_password(new_password), selected_username),
                                )
                        db.log_audit(
                            auth.current_username(),
                            "تعديل",
                            "المستخدمون",
                            selected_username,
                            f"الدور: {new_role_label} • نشط: {is_active}",
                        )
                        st.success("تم تحديث بيانات المستخدم بنجاح.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"تعذر تحديث المستخدم: {error}")

            st.divider()
            st.markdown("##### حذف الحساب")
            if selected_username == auth.current_username():
                st.info("لا يمكنك حذف حسابك الحالي.")
            else:
                active_admins = int(
                    db.scalar(
                        "SELECT COUNT(*) FROM Users "
                        "WHERE Role='admin' AND IsActive=1",
                        default=0,
                    )
                    or 0
                )
                is_last_admin = (
                    str(selected_user.get("Role")) == auth.ROLE_ADMIN
                    and int(selected_user.get("IsActive") or 0) == 1
                    and active_admins <= 1
                )
                if is_last_admin:
                    st.warning("لا يمكن حذف آخر مدير نظام نشط.")
                confirm = st.checkbox(
                    "أؤكد رغبتي في حذف هذا الحساب",
                    key="confirm_delete_user",
                )
                if st.button(
                    "حذف الحساب نهائياً",
                    icon=":material/delete:",
                    width="stretch",
                    key="delete_user_button",
                ):
                    if not confirm:
                        st.error("يرجى تأكيد الحذف أولاً.")
                    elif is_last_admin:
                        st.error("لا يمكن حذف آخر مدير نظام نشط.")
                    else:
                        db.execute(
                            "DELETE FROM Users WHERE Username=?",
                            (selected_username,),
                        )
                        db.log_audit(
                            auth.current_username(),
                            "حذف",
                            "المستخدمون",
                            selected_username,
                        )
                        st.success("تم حذف المستخدم بنجاح.")
                        st.rerun()

st.divider()
ui.section_title("حسابات النظام", "جميع المستخدمين وصلاحياتهم وحالة الدخول")

display = users.copy()
if not display.empty:
    display = display.rename(
        columns={
            "Username": "اسم المستخدم",
            "FullName": "الاسم الكامل",
            "CreatedAt": "تاريخ الإنشاء",
            "LastLoginAt": "آخر دخول",
        }
    )
    ui.render_df(
        display,
        columns=[
            "اسم المستخدم",
            "الاسم الكامل",
            "الدور",
            "الحالة",
            "تاريخ الإنشاء",
            "آخر دخول",
        ],
        alt="جدول المستخدمين",
    )
    ui.csv_download_button(
        display[
            [
                "اسم المستخدم",
                "الاسم الكامل",
                "الدور",
                "الحالة",
                "تاريخ الإنشاء",
                "آخر دخول",
            ]
        ],
        "users.csv",
        key="download_users",
    )
else:
    ui.empty_state("لا يوجد مستخدمون مسجلون.", "👥")
