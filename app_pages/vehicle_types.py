"""أنواع المركبات: إضافة وتعديل وحذف أنواع الأسطول."""

from __future__ import annotations

import sqlite3

import streamlit as st

from core import auth, db, ui
from core.utils import clean_text

auth.require_login()
ui.page_header(
    "أنواع المركبات",
    "تصنيفات الأسطول المستخدمة في سجلات المركبات والتقارير",
    "🏷️",
)

types = db.read_df(
    """
    SELECT vt.TypeName AS "نوع المركبة",
           (SELECT COUNT(*) FROM Buses b WHERE b.VehicleType = vt.TypeName)
               AS "عدد المركبات"
      FROM VehicleTypes vt
     ORDER BY vt.TypeName
    """
)

if not types.empty:
    metric_columns = st.columns(3)
    metric_columns[0].metric("إجمالي الأنواع", f"{len(types):,}")
    metric_columns[1].metric(
        "أنواع مستخدمة",
        f"{int((types['عدد المركبات'] > 0).sum()):,}",
    )
    metric_columns[2].metric(
        "إجمالي المركبات المصنفة",
        f"{int(types['عدد المركبات'].sum()):,}",
    )
    st.write("")

# ---------------------------------------------------------------------------
# إضافة نوع
# ---------------------------------------------------------------------------
with st.expander("➕ إضافة نوع مركبة جديد", expanded=types.empty):
    with st.form("add_vehicle_type_form", clear_on_submit=True):
        new_type = st.text_input(
            "اسم نوع المركبة *",
            placeholder="مثال: حافلة كوستر",
        )
        submitted = st.form_submit_button(
            "حفظ النوع",
            type="primary",
            width="stretch",
        )

    if submitted:
        name = clean_text(new_type, 80)
        if not name:
            st.error("يرجى إدخال اسم نوع المركبة.")
        else:
            try:
                db.execute(
                    "INSERT INTO VehicleTypes (TypeName) VALUES (?)",
                    (name,),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "أنواع المركبات",
                    name,
                )
                st.success("تمت إضافة نوع المركبة بنجاح.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("هذا النوع مسجل مسبقاً.")
            except Exception as error:
                st.error(f"تعذر حفظ النوع: {error}")

# ---------------------------------------------------------------------------
# تعديل وحذف
# ---------------------------------------------------------------------------
if not types.empty:
    with st.expander("⚙️ تعديل أو حذف نوع مركبة"):
        type_names = types["نوع المركبة"].astype(str).tolist()
        selected_type = st.selectbox(
            "اختر نوع المركبة",
            type_names,
            key="manage_vehicle_type",
        )
        usage = int(
            db.scalar(
                "SELECT COUNT(*) FROM Buses WHERE VehicleType = ?",
                (selected_type,),
                default=0,
            )
            or 0
        )
        st.caption(f"عدد المركبات المرتبطة بهذا النوع: {usage:,}")

        with st.form("edit_vehicle_type_form"):
            new_name = st.text_input(
                "الاسم الجديد",
                value=selected_type,
            )
            save_changes = st.form_submit_button(
                "حفظ التعديلات",
                type="primary",
                width="stretch",
            )

        if save_changes:
            clean_name = clean_text(new_name, 80)
            if not clean_name:
                st.error("الاسم لا يمكن أن يكون فارغاً.")
            elif clean_name == selected_type:
                st.info("لم يتم تغيير الاسم.")
            else:
                try:
                    with db.get_conn() as connection:
                        connection.execute(
                            "UPDATE VehicleTypes SET TypeName=? WHERE TypeName=?",
                            (clean_name, selected_type),
                        )
                        connection.execute(
                            "UPDATE Buses SET VehicleType=? WHERE VehicleType=?",
                            (clean_name, selected_type),
                        )
                    db.log_audit(
                        auth.current_username(),
                        "تعديل",
                        "أنواع المركبات",
                        selected_type,
                        f"إلى: {clean_name}",
                    )
                    st.success("تم تحديث نوع المركبة والمركبات المرتبطة به.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("الاسم الجديد مسجل مسبقاً.")
                except Exception as error:
                    st.error(f"تعذر تحديث النوع: {error}")

        st.divider()
        st.markdown("##### حذف النوع")
        if usage:
            st.warning(
                "لا يمكن حذف هذا النوع لوجود مركبات مرتبطة به. "
                "قم بتغيير نوع تلك المركبات أولاً."
            )
        confirm = st.checkbox(
            "أؤكد رغبتي في حذف هذا النوع",
            key="confirm_delete_vehicle_type",
        )
        if st.button(
            "حذف النوع نهائياً",
            icon=":material/delete:",
            width="stretch",
            key="delete_vehicle_type_button",
        ):
            if not confirm:
                st.error("يرجى تأكيد الحذف أولاً.")
            elif usage:
                st.error("لا يمكن حذف نوع مرتبط بمركبات.")
            else:
                db.execute(
                    "DELETE FROM VehicleTypes WHERE TypeName=?",
                    (selected_type,),
                )
                db.log_audit(
                    auth.current_username(),
                    "حذف",
                    "أنواع المركبات",
                    selected_type,
                )
                st.success("تم حذف النوع بنجاح.")
                st.rerun()

st.divider()
ui.section_title("الأنواع المسجلة", "جميع تصنيفات المركبات في النظام")
ui.render_df(
    types,
    alt="جدول أنواع المركبات",
    empty_message="لا توجد أنواع مركبات مسجلة.",
)
ui.csv_download_button(
    types,
    "vehicle_types.csv",
    key="download_vehicle_types",
)
