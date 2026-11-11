"""تقارير الفحص الدوري: إضافة، تصفية، تعديل، حذف، وعرض مرفقات الفحص."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import auth, db, ui
from core.services import bus_id_from_label, bus_labels, sync_bus_inspection
from core.utils import (
    clean_multiline,
    days_until,
    inspection_status,
    parse_date,
    save_upload,
    to_int,
)

auth.require_login()
ui.page_header(
    "تقارير الفحص الدوري",
    "متابعة مواعيد انتهاء الفحص الدوري وحالة المركبات والمرفقات",
    "📋",
)

buses = db.read_df(
    "SELECT BusID, VehicleType, Model FROM Buses ORDER BY BusID"
)

reports = db.read_df(
    """
    SELECT i.*, COALESCE(b.VehicleType, 'غير متوفر') AS VehicleType, b.Model
      FROM InspectionReports i
      LEFT JOIN Buses b ON b.BusID = i.BusID
     ORDER BY COALESCE(i.ExpiryDate, '') ASC, i.ReportID DESC
    """
)

if not reports.empty:
    reports["_expiry"] = pd.to_datetime(reports["ExpiryDate"], errors="coerce")

today = date.today()
today_ts = pd.Timestamp(today)

if not reports.empty:
    expired = reports[reports["_expiry"] < today_ts]
    upcoming = reports[
        (reports["_expiry"] >= today_ts)
        & (reports["_expiry"] <= pd.Timestamp(today + pd.Timedelta(days=30)))
    ]
else:
    expired = reports
    upcoming = reports

metric_cols = st.columns(3)
metric_cols[0].metric("إجمالي تقارير الفحص", f"{len(reports):,}")
metric_cols[1].metric("فحوصات منتهية", f"{len(expired):,}", delta_color="inverse")
metric_cols[2].metric("فحوصات قريبة الانتهاء", f"{len(upcoming):,}")
st.write("")

# ---------------------------------------------------------------------------
# إضافة تقرير فحص جديد
# ---------------------------------------------------------------------------
with st.expander("➕ إضافة تقرير فحص دوري جديد"):
    labels = bus_labels()
    if not labels:
        st.warning("يرجى إضافة مركبات أولاً قبل تسجيل تقارير الفحص.")
    else:
        with st.form("add_inspection_form", clear_on_submit=True):
            first, second = st.columns(2)
            with first:
                selected_bus_label = st.selectbox("رقم المركبة *", list(labels.values()))
                test_date = st.date_input("تاريخ الفحص", value=today)
                expiry_date = st.date_input("تاريخ انتهاء الفحص", value=today)
            with second:
                result = st.selectbox(
                    "نتيجة الفحص *",
                    ["اجتاز الفحص بنجاح", "راسب", "يحتاج إعادة فحص"],
                )
                report_file = st.file_uploader(
                    "إرفاق مستند/تقرير الفحص (PDF أو صورة)",
                    type=["pdf", "png", "jpg", "jpeg"],
                )
                notes = st.text_area("ملاحظات")

            submitted = st.form_submit_button(
                "حفظ تقرير الفحص",
                type="primary",
                width="stretch",
            )

        if submitted:
            target_bus_id = bus_id_from_label(selected_bus_label)
            if not target_bus_id:
                st.error("يرجى اختيار رقم المركبة.")
            elif expiry_date < test_date:
                st.error("تاريخ الانتهاء لا يمكن أن يكون قبل تاريخ الفحص.")
            else:
                try:
                    stored_file = (
                        save_upload("inspections", f"insp_{target_bus_id}", report_file)
                        if report_file is not None
                        else ""
                    )
                    db.execute(
                        """
                        INSERT INTO InspectionReports (
                            BusID, InspectionDate, ExpiryDate, ResultStatus,
                            ReportFile, Notes, CreatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            target_bus_id,
                            str(test_date),
                            str(expiry_date),
                            result,
                            stored_file,
                            clean_multiline(notes),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
                    sync_bus_inspection(target_bus_id)
                    db.log_audit(
                        auth.current_username(),
                        "إضافة",
                        "الفحص الدوري",
                        target_bus_id,
                        f"نتيجة: {result} • ينتهي في: {expiry_date}",
                    )
                    st.success("تم حفظ تقرير الفحص بنجاح.")
                    st.rerun()
                except Exception as error:
                    st.error(f"تعذر حفظ التقرير: {error}")

# ---------------------------------------------------------------------------
# تصفية تقارير الفحص
# ---------------------------------------------------------------------------
st.divider()
ui.section_title("تصفية تقارير الفحص", "ابحث في تقارير الفحص الدوري")

filter_first, filter_second = st.columns(2)
with filter_first:
    bus_filter_options = (
        ["-- الكل --", *buses["BusID"].astype(str).tolist()]
        if not buses.empty
        else ["-- الكل --"]
    )
    selected_bus_filter = st.selectbox(
        "تصفية حسب المركبة",
        bus_filter_options,
        key="insp_bus_filter",
    )
with filter_second:
    status_filter_options = [
        "-- الكل --",
        "ساري",
        "قريب الانتهاء",
        "منتهي",
    ]
    selected_status_filter = st.selectbox(
        "تصفية حسب الحالة",
        status_filter_options,
        key="insp_status_filter",
    )

filtered = reports.copy() if not reports.empty else reports
if not filtered.empty:
    if selected_bus_filter != "-- الكل --":
        filtered = filtered[filtered["BusID"].astype(str) == selected_bus_filter]
    
    filtered["أيام متبقية"] = filtered["ExpiryDate"].apply(days_until)
    filtered["حالة الفحص"] = filtered["أيام متبقية"].apply(inspection_status)

    if selected_status_filter != "-- الكل --":
        filtered = filtered[filtered["حالة الفحص"] == selected_status_filter]

st.caption(f"عدد النتائج: {len(filtered):,} سجل")

# ---------------------------------------------------------------------------
# استعراض وإدارة تقارير الفحص ببطاقات تفاعلية وأزرار مباشرة
# ---------------------------------------------------------------------------
if filtered.empty:
    ui.empty_state("لا توجد تقارير فحص مطابقة لخيارات التصفية.", "📋")
else:
    st.divider()
    ui.section_title("استعراض وإدارة التقارير", "كل تقرير يضم أزرار التحكم ومرفقاته مباشرة")

    for _, row in filtered.iterrows():
        report_id = int(row["ReportID"])
        bus_id = str(row.get("BusID") or "—")
        v_type = str(row.get("VehicleType") or "—")
        test_d = str(row.get("InspectionDate") or "—")
        expiry_d = str(row.get("ExpiryDate") or "—")
        res = str(row.get("ResultStatus") or "—")
        status_val = str(row.get("حالة الفحص") or "—")
        days_rem = to_int(row.get("أيام متبقية"), 0)
        notes_val = str(row.get("Notes") or "لا توجد ملاحظات")
        report_file = row.get("ReportFile")

        with st.container(border=True):
            cols = st.columns([2, 1.5, 1.5, 2, 1.5])
            with cols[0]:
                st.markdown(f"**المركبة:** {bus_id}")
                st.caption(f"النوع: {v_type}")
            with cols[1]:
                st.markdown(f"**تاريخ الفحص:** {test_d}")
                st.caption(f"الانتهاء: {expiry_d}")
            with cols[2]:
                st.markdown(f"**النتيجة:** {res}")
                st.caption(f"الحالة: {status_val} ({days_rem} يوم)")
            with cols[3]:
                st.markdown(f"**ملاحظات:** {notes_val}")
            with cols[4]:
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if st.button("✏️", key=f"edit_insp_{report_id}", help="تعديل التقرير"):
                        st.session_state[f"editing_insp_id"] = report_id
                with btn_cols[1]:
                    if st.button("🗑️", key=f"del_insp_{report_id}", help="حذف التقرير"):
                        st.session_state[f"deleting_insp_id"] = report_id
                with btn_cols[2]:
                    if report_file:
                        ui.download_file_button(
                            report_file,
                            "📄",
                            key=f"dl_insp_file_{report_id}",
                        )
                    else:
                        st.markdown("—")

        # واجهة التعديل السريع للتقرير
        if st.session_state.get(f"editing_insp_id") == report_id:
            with st.form(f"edit_insp_form_{report_id}"):
                st.markdown(f"##### تعديل تقرير الفحص رقم #{report_id}")
                f1, f2 = st.columns(2)
                with f1:
                    e_test = st.date_input("تاريخ الفحص", value=parse_date(test_d) or today, key=f"e_test_{report_id}")
                    e_expiry = st.date_input("تاريخ الانتهاء", value=parse_date(expiry_d) or today, key=f"e_expiry_{report_id}")
                    result_options = ["اجتاز الفحص بنجاح", "راسب", "يحتاج إعادة فحص"]
                    e_res = st.selectbox(
                        "نتيجة الفحص",
                        result_options,
                        index=(
                            result_options.index(res)
                            if res in result_options
                            else 0
                        ),
                        key=f"e_res_{report_id}",
                    )
                with f2:
                    e_file = st.file_uploader("استبدال مرفق الفحص", type=["pdf", "png", "jpg", "jpeg"], key=f"e_file_{report_id}")
                    e_notes = st.text_area("ملاحظات", value=notes_val, key=f"e_notes_{report_id}")

                sub1, sub2 = st.columns(2)
                with sub1:
                    if st.form_submit_button("حفظ التعديلات", type="primary", width="stretch"):
                        try:
                            final_file = report_file
                            if e_file is not None:
                                final_file = save_upload("inspections", f"insp_{bus_id}", e_file)
                            
                            db.execute(
                                """
                                UPDATE InspectionReports
                                   SET InspectionDate=?, ExpiryDate=?, ResultStatus=?,
                                       ReportFile=?, Notes=?
                                 WHERE ReportID=?
                                """,
                                (
                                    str(e_test),
                                    str(e_expiry),
                                    e_res,
                                    str(final_file or ""),
                                    clean_multiline(e_notes),
                                    report_id,
                                ),
                            )
                            sync_bus_inspection(bus_id)
                            db.log_audit(auth.current_username(), "تعديل", "الفحص الدوري", report_id, f"تحديث فحص المركبة {bus_id}")
                            st.session_state.pop(f"editing_insp_id", None)
                            st.success("تم تحديث تقرير الفحص بنجاح.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"خطأ: {err}")
                with sub2:
                    if st.form_submit_button("إلغاء", width="stretch"):
                        st.session_state.pop(f"editing_insp_id", None)
                        st.rerun()

        # واجهة تأكيد الحذف
        if st.session_state.get(f"deleting_insp_id") == report_id:
            with st.container(border=True):
                st.warning(f"هل أنت متأكد من رغبتك في حذف تقرير الفحص رقم #{report_id} نهائياً؟")
                d_c1, d_c2 = st.columns(2)
                with d_c1:
                    if st.button("نعم، احذف نهائياً", key=f"conf_del_insp_{report_id}", type="primary"):
                        db.execute("DELETE FROM InspectionReports WHERE ReportID=?", (report_id,))
                        sync_bus_inspection(bus_id)
                        db.log_audit(auth.current_username(), "حذف", "الفحص الدوري", report_id, f"فحص مركبة {bus_id}")
                        st.session_state.pop(f"deleting_insp_id", None)
                        st.success("تم حذف التقرير بنجاح.")
                        st.rerun()
                with d_c2:
                    if st.button("تراجع", key=f"canc_del_insp_{report_id}"):
                        st.session_state.pop(f"deleting_insp_id", None)
                        st.rerun()