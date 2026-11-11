"""الورش ومراكز الصيانة: إدارة الأسماء المستخدمة في سجلات الصيانة."""

from __future__ import annotations

import sqlite3

import streamlit as st

from core import auth, db, ui
from core.utils import clean_text

auth.require_login()
ui.page_header(
    "الورش ومراكز الصيانة",
    "دليل الورش المعتمدة وربطها بسجلات أعمال الصيانة",
    "🏢",
)

workshops = db.read_df(
    """
    SELECT w.WorkshopName AS "اسم الورشة / المركز",
           (SELECT COUNT(*) FROM Logs l WHERE l.Workshop = w.WorkshopName)
               AS "عدد السجلات"
      FROM Workshops w
     ORDER BY w.WorkshopName
    """
)

if not workshops.empty:
    metric_columns = st.columns(3)
    metric_columns[0].metric("إجمالي الورش", f"{len(workshops):,}")
    metric_columns[1].metric(
        "ورش مستخدمة",
        f"{int((workshops['عدد السجلات'] > 0).sum()):,}",
    )
    metric_columns[2].metric(
        "سجلات صيانة مرتبطة",
        f"{int(workshops['عدد السجلات'].sum()):,}",
    )
    st.write("")

with st.expander("➕ إضافة ورشة أو مركز صيانة", expanded=workshops.empty):
    with st.form("add_workshop_form", clear_on_submit=True):
        new_workshop = st.text_input(
            "اسم الورشة أو المركز *",
            placeholder="مثال: ورشة النور المركزية",
        )
        submitted = st.form_submit_button(
            "حفظ الورشة",
            type="primary",
            width="stretch",
        )

    if submitted:
        name = clean_text(new_workshop, 120)
        if not name:
            st.error("يرجى إدخال اسم الورشة.")
        else:
            try:
                db.execute(
                    "INSERT INTO Workshops (WorkshopName) VALUES (?)",
                    (name,),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "الورش",
                    name,
                )
                st.success("تمت إضافة الورشة بنجاح.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("هذه الورشة مسجلة مسبقاً.")
            except Exception as error:
                st.error(f"تعذر حفظ الورشة: {error}")

if not workshops.empty:
    with st.expander("⚙️ تعديل أو حذف ورشة"):
        workshop_names = workshops["اسم الورشة / المركز"].astype(str).tolist()
        selected_workshop = st.selectbox(
            "اختر الورشة",
            workshop_names,
            key="manage_workshop",
        )
        usage = int(
            db.scalar(
                "SELECT COUNT(*) FROM Logs WHERE Workshop=?",
                (selected_workshop,),
                default=0,
            )
            or 0
        )
        st.caption(f"عدد سجلات الصيانة المرتبطة: {usage:,}")

        with st.form("edit_workshop_form"):
            new_name = st.text_input("الاسم الجديد", value=selected_workshop)
            save_changes = st.form_submit_button(
                "حفظ التعديلات",
                type="primary",
                width="stretch",
            )

        if save_changes:
            clean_name = clean_text(new_name, 120)
            if not clean_name:
                st.error("اسم الورشة لا يمكن أن يكون فارغاً.")
            elif clean_name == selected_workshop:
                st.info("لم يتم تغيير الاسم.")
            else:
                try:
                    with db.get_conn() as connection:
                        connection.execute(
                            "UPDATE Workshops SET WorkshopName=? WHERE WorkshopName=?",
                            (clean_name, selected_workshop),
                        )
                        connection.execute(
                            "UPDATE Logs SET Workshop=? WHERE Workshop=?",
                            (clean_name, selected_workshop),
                        )
                    db.log_audit(
                        auth.current_username(),
                        "تعديل",
                        "الورش",
                        selected_workshop,
                        f"إلى: {clean_name}",
                    )
                    st.success("تم تحديث الورشة وسجلات الصيانة المرتبطة بها.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("الاسم الجديد مسجل مسبقاً.")
                except Exception as error:
                    st.error(f"تعذر تحديث الورشة: {error}")

        st.divider()
        st.markdown("##### حذف الورشة")
        if usage:
            st.warning(
                "لا يمكن حذف ورشة مرتبطة بسجلات صيانة. "
                "قم بتعديل اسم الورشة في السجلات أولاً إن لزم."
            )
        confirm = st.checkbox(
            "أؤكد رغبتي في حذف هذه الورشة",
            key="confirm_delete_workshop",
        )
        if st.button(
            "حذف الورشة نهائياً",
            icon=":material/delete:",
            width="stretch",
            key="delete_workshop_button",
        ):
            if not confirm:
                st.error("يرجى تأكيد الحذف أولاً.")
            elif usage:
                st.error("لا يمكن حذف ورشة مرتبطة بسجلات.")
            else:
                db.execute(
                    "DELETE FROM Workshops WHERE WorkshopName=?",
                    (selected_workshop,),
                )
                db.log_audit(
                    auth.current_username(),
                    "حذف",
                    "الورش",
                    selected_workshop,
                )
                st.success("تم حذف الورشة بنجاح.")
                st.rerun()

st.divider()
ui.section_title("الورش المسجلة", "جميع ورش ومراكز الصيانة في النظام")
ui.render_df(
    workshops,
    alt="جدول الورش",
    empty_message="لا توجد ورش مسجلة.",
)
ui.csv_download_button(
    workshops,
    "workshops.csv",
    key="download_workshops",
)
