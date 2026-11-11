"""أنواع الصيانة: إضافة وتعديل وحذف مسميات أعمال وصيانة الأسطول."""

from __future__ import annotations

import streamlit as st

from core import auth, db, ui
from core.utils import clean_text

auth.require_login()
ui.page_header(
    "أنواع الصيانة",
    "إدارة مسميات أعمال الصيانة والدعم الفني المتاحة في النظام",
    "🛠️",
)

# إضافة نوع صيانة جديد
with st.expander("➕ إضافة نوع صيانة جديد"):
    with st.form("add_maintenance_type_form", clear_on_submit=True):
        job_type_name = st.text_input(
            "اسم نوع العمل / الصيانة *",
            placeholder="مثال: صيانة دورية، تغيير إطارات، إصلاح مكيف...",
        )
        submitted = st.form_submit_button(
            "حفظ نوع الصيانة",
            type="primary",
            width="stretch",
        )

    if submitted:
        name_clean = clean_text(job_type_name, 100)
        if not name_clean:
            st.error("اسم نوع الصيانة مطلوب.")
        else:
            try:
                db.execute(
                    """
                    INSERT INTO MaintenanceTypes (JobTypeName)
                    VALUES (?)
                    """,
                    (name_clean,),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "أنواع الصيانة",
                    name_clean,
                    "إضافة نوع صيانة جديد",
                )
                st.success("تمت إضافة نوع الصيانة بنجاح.")
                st.rerun()
            except Exception as error:
                st.error(f"تعذر الحفظ (ربما الاسم موجود مسبقاً): {error}")

st.divider()
ui.section_title("قائمة أنواع الصيانة المسجلة", "استعراض وتعديل وحذف أنواع الصيانة")

# قراءة الأسماء الموجودة في الجدول فعلياً
types_df = db.read_df(
    "SELECT JobTypeName FROM MaintenanceTypes ORDER BY JobTypeName"
)

if types_df.empty:
    ui.empty_state("لا توجد أنواع صيانة مسجلة حالياً.", "🛠️")
else:
    display_df = types_df.rename(
        columns={
            "JobTypeName": "اسم نوع الصيانة",
        }
    )
    
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
    )

    st.divider()
    ui.section_title("إدارة نوع صيانة محدد", "تعديل أو حذف نوع صيانة")

    type_options = {
        f"{row['JobTypeName']}": row
        for _, row in types_df.iterrows()
    }
    
    selected_option = st.selectbox(
        "اختر نوع الصيانة للتعامل معه",
        list(type_options.keys()),
        key="select_maint_type",
    )
    
    selected_row = type_options[selected_option]
    current_name = str(selected_row["JobTypeName"])

    with st.form("edit_maint_type_form"):
        new_name = st.text_input("تعديل اسم نوع الصيانة", value=current_name)
        update_submitted = st.form_submit_button("حفظ التعديلات", type="primary", width="stretch")

    if update_submitted:
        cleaned_new_name = clean_text(new_name, 100)
        if not cleaned_new_name:
            st.error("اسم نوع الصيانة لا يمكن أن يكون فارغاً.")
        else:
            try:
                db.execute(
                    "UPDATE MaintenanceTypes SET JobTypeName=? WHERE JobTypeName=?",
                    (cleaned_new_name, current_name),
                )
                db.log_audit(auth.current_username(), "تعديل", "أنواع الصيانة", current_name, f"تعديل إلى: {cleaned_new_name}")
                st.success("تم تحديث نوع الصيانة بنجاح.")
                st.rerun()
            except Exception as error:
                st.error(f"تعذر التحديث: {error}")

    if auth.is_admin():
        st.write("")
        confirm_del = st.checkbox("أؤكد رغبتي في حذف نوع الصيانة هذا", key="confirm_del_maint_type")
        if st.button("حذف نوع الصيانة نهائياً", icon=":material/delete:", width="stretch"):
            if not confirm_del:
                st.error("يرجى تأكيد الحذف أولاً.")
            else:
                try:
                    db.execute("DELETE FROM MaintenanceTypes WHERE JobTypeName=?", (current_name,))
                    db.log_audit(auth.current_username(), "حذف", "أنواع الصيانة", current_name, current_name)
                    st.success("تم حذف نوع الصيانة بنجاح.")
                    st.rerun()
                except Exception as error:
                    st.error(f"تعذر الحذف: {error}")
    else:
        st.caption("حذف أنواع الصيانة متاح لمدير النظام فقط.")