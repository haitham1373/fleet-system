"""سجلات الصيانة والفواتير: إضافة وتصفية وتعديل سجلات الصيانة والمصروفات."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import auth, db, ui
from core.services import bus_id_from_label, bus_labels
from core.utils import (
    clean_multiline,
    money,
    parse_date,
    save_upload,
    to_float,
)

auth.require_login()
ui.page_header(
    "سجلات الصيانة والفواتير",
    "أعمال الصيانة والمصروفات العامة وحالة الفواتير والمرفقات",
    "🧾",
)

buses = db.read_df(
    "SELECT BusID, VehicleType, Model FROM Buses ORDER BY BusID"
)
vehicle_types = [
    str(value)
    for value in db.fetch_column(
        "SELECT TypeName FROM VehicleTypes ORDER BY TypeName"
    )
]
workshops = [
    str(value)
    for value in db.fetch_column(
        "SELECT WorkshopName FROM Workshops ORDER BY WorkshopName"
    )
]
job_types = [
    str(value)
    for value in db.fetch_column(
        "SELECT JobTypeName FROM MaintenanceTypes ORDER BY JobTypeName"
    )
]

if not workshops:
    workshops = ["مركز الصيانة"]
if not job_types:
    job_types = ["صيانة دورية"]

logs = db.read_df(
    """
    SELECT l.*, COALESCE(b.VehicleType, 'مصروفات عامة') AS VehicleType,
           b.Model
      FROM Logs l
      LEFT JOIN Buses b ON b.BusID = l.BusID
     ORDER BY COALESCE(l.DoneDate, '') DESC, l.LogID DESC
    """
)

if not logs.empty:
    logs["_date"] = pd.to_datetime(logs["DoneDate"], errors="coerce")
    logs["_cost"] = pd.to_numeric(logs["Cost"], errors="coerce").fillna(0.0)
    logs["_status"] = logs["InvoiceStatus"].fillna("").astype(str).str.strip()

today = date.today()
current_month = today.strftime("%Y-%m")
unpaid = logs[logs["_status"] == "غير مدفوع"] if not logs.empty else logs
month_logs = (
    logs[logs["_date"].dt.strftime("%Y-%m") == current_month]
    if not logs.empty
    else logs
)

metric_columns = st.columns(4)
metric_columns[0].metric("إجمالي السجلات", f"{len(logs):,}")
metric_columns[1].metric(
    "إجمالي التكاليف",
    money(float(logs["_cost"].sum()) if not logs.empty else 0),
)
metric_columns[2].metric(
    "فواتير غير مدفوعة",
    money(float(unpaid["_cost"].sum()) if not unpaid.empty else 0),
    delta=f"{len(unpaid):,} سجل" if not unpaid.empty else None,
    delta_color="inverse",
)
metric_columns[3].metric(
    "تكلفة الشهر الحالي",
    money(float(month_logs["_cost"].sum()) if not month_logs.empty else 0),
)
st.write("")

# ---------------------------------------------------------------------------
# إضافة سجل
# ---------------------------------------------------------------------------
with st.expander("➕ إضافة سجل صيانة أو مصروف جديد"):
    record_kind = st.radio(
        "نوع السجل",
        ["سجل مركبة", "مصروفات عامة"],
        horizontal=True,
        key="log_record_kind",
    )

    selected_vehicle_type = "-- الكل --"
    if record_kind == "سجل مركبة":
        vehicle_type_options = (
            sorted(
                {
                    str(value).strip()
                    for value in buses["VehicleType"].dropna().tolist()
                    if str(value).strip()
                }
            )
            if not buses.empty
            else []
        )
        selected_vehicle_type = st.selectbox(
            "نوع المركبة (لتصفية أرقام المركبات)",
            ["-- الكل --", *vehicle_type_options],
            key="log_vehicle_type",
        )

    with st.form("add_log_form", clear_on_submit=True):
        first, second, third = st.columns(3)

        with first:
            if record_kind == "سجل مركبة":
                labels = bus_labels()
                if selected_vehicle_type != "-- الكل --":
                    allowed_ids = set(
                        buses.loc[
                            buses["VehicleType"].astype(str).str.strip()
                            == selected_vehicle_type,
                            "BusID",
                        ].astype(str)
                    )
                    labels = {
                        bus_id: label
                        for bus_id, label in labels.items()
                        if bus_id in allowed_ids
                    }
                if labels:
                    selected_bus_label = st.selectbox(
                        "رقم المركبة *",
                        list(labels.values()),
                        key=f"log_bus_for_{selected_vehicle_type}",
                    )
                else:
                    selected_bus_label = None
                    st.warning("لا توجد مركبات مسجلة ضمن النوع المحدد.")
            else:
                selected_bus_label = None
                st.text_input(
                    "البند",
                    value="مصروفات عامة",
                    disabled=True,
                )
            log_date = st.date_input("تاريخ الصيانة", value=today)

        with second:
            job_type = st.selectbox("نوع العمل *", job_types)
            cost = st.number_input(
                "التكلفة (ريال) *",
                min_value=0.0,
                value=0.0,
                step=50.0,
                format="%.2f",
            )

        with third:
            workshop = st.selectbox("الورشة / المركز *", workshops)
            invoice_status = st.selectbox(
                "حالة الفاتورة",
                ["مدفوع", "غير مدفوع"],
            )

        invoice_file = st.file_uploader(
            "إرفاق فاتورة الصيانة (PDF أو صورة)",
            type=["pdf", "png", "jpg", "jpeg"],
        )
        notes = st.text_area("ملاحظات إضافية")

        submitted = st.form_submit_button(
            "حفظ السجل",
            type="primary",
            width="stretch",
        )

    if submitted:
        target_bus_id = (
            bus_id_from_label(selected_bus_label)
            if record_kind == "سجل مركبة" and selected_bus_label
            else "مصروفات عامة"
        )

        if record_kind == "سجل مركبة" and not target_bus_id:
            st.error("يرجى اختيار رقم المركبة.")
        else:
            try:
                stored_file = (
                    save_upload("invoices", f"log_{target_bus_id}", invoice_file)
                    if invoice_file is not None
                    else ""
                )
                db.execute(
                    """
                    INSERT INTO Logs (
                        BusID, DoneDate, JobType, Cost, Workshop,
                        InvoiceStatus, InvoiceFile, Notes, CreatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_bus_id,
                        str(log_date),
                        job_type,
                        float(cost),
                        workshop,
                        invoice_status,
                        stored_file,
                        clean_multiline(notes),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "سجلات الصيانة",
                    target_bus_id,
                    f"{job_type} • {cost:,.2f} ريال",
                )
                st.success("تم حفظ السجل بنجاح.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"تعذر حفظ السجل: {error}")

# ---------------------------------------------------------------------------
# تصفية السجلات وعرضها
# ---------------------------------------------------------------------------
st.divider()
ui.section_title("تصفية السجلات", "ابحث في سجلات الصيانة والمصروفات")

filter_first, filter_second, filter_third = st.columns([1, 1, 1])
with filter_first:
    type_filter = st.selectbox(
        "نوع المركبة / البند",
        ["-- الكل --", "مصروفات عامة", *vehicle_types],
        key="logs_type_filter",
    )
with filter_second:
    if type_filter == "مصروفات عامة":
        bus_options = ["مصروفات عامة"]
    elif type_filter == "-- الكل --":
        bus_options = (
            ["مصروفات عامة", *buses["BusID"].astype(str).tolist()]
            if not buses.empty
            else ["مصروفات عامة"]
        )
    else:
        bus_options = buses.loc[
            buses["VehicleType"].astype(str) == type_filter, "BusID"
        ].astype(str).tolist()
    bus_filter = st.selectbox(
        "رقم المركبة",
        ["-- الكل --", *bus_options],
        key="logs_bus_filter",
    )
with filter_third:
    date_mode = st.selectbox(
        "الفترة",
        ["كل التواريخ", "تاريخ محدد", "الشهر الحالي", "فترة مخصصة"],
        key="logs_date_mode",
    )

start_date = end_date = None
if date_mode == "تاريخ محدد":
    start_date = st.date_input(
        "اختر التاريخ",
        value=today,
        key="logs_single_date",
    )
elif date_mode == "فترة مخصصة":
    range_first, range_second = st.columns(2)
    with range_first:
        start_date = st.date_input(
            "من تاريخ",
            value=today.replace(day=1),
            key="logs_start_date",
        )
    with range_second:
        end_date = st.date_input(
            "إلى تاريخ",
            value=today,
            key="logs_end_date",
        )

search_term = st.text_input(
    "بحث في نوع العمل أو الورشة أو الملاحظات",
    placeholder="اكتب كلمة للبحث...",
    key="logs_search",
)

filtered = logs.copy() if not logs.empty else logs
if not filtered.empty:
    if type_filter == "مصروفات عامة":
        filtered = filtered[filtered["BusID"] == "مصروفات عامة"]
    elif type_filter != "-- الكل --":
        filtered = filtered[filtered["VehicleType"].astype(str) == type_filter]

    if bus_filter != "-- الكل --":
        filtered = filtered[filtered["BusID"].astype(str) == bus_filter]

    if date_mode == "تاريخ محدد" and start_date:
        filtered = filtered[filtered["_date"].dt.date == start_date]
    elif date_mode == "الشهر الحالي":
        filtered = filtered[
            filtered["_date"].dt.strftime("%Y-%m") == current_month
        ]
    elif date_mode == "فترة مخصصة" and start_date and end_date:
        filtered = filtered[
            (filtered["_date"].dt.date >= start_date)
            & (filtered["_date"].dt.date <= end_date)
        ]

    if search_term.strip():
        term = search_term.strip().lower()
        search_columns = ["JobType", "Workshop", "Notes", "BusID"]
        mask = pd.Series(False, index=filtered.index)
        for column in search_columns:
            mask = mask | filtered[column].astype(str).str.lower().str.contains(
                term, na=False
            )
        filtered = filtered[mask]

st.caption(f"عدد النتائج: {len(filtered):,} سجل")

# ---------------------------------------------------------------------------
# استعراض وإدارة السجلات في بطاقات تفاعلية مع أزرار (تعديل، حذف، الفاتورة)
# ---------------------------------------------------------------------------
if filtered.empty:
    ui.empty_state("لا توجد سجلات مطابقة لخيارات التصفية.", "🧾")
else:
    st.divider()
    ui.section_title("استعراض وإدارة السجلات", "كل سجل يضم أزرار التحكم الخاصة به مباشرة")

    for _, row in filtered.iterrows():
        log_id = int(row["LogID"])
        bus_id = str(row.get("BusID") or "—")
        v_type = str(row.get("VehicleType") or "—")
        done_date = str(row.get("DoneDate") or "—")
        job = str(row.get("JobType") or "—")
        cost_val = float(row.get("Cost") or 0.0)
        workshop_name = str(row.get("Workshop") or "—")
        inv_status = str(row.get("InvoiceStatus") or "—")
        notes_val = str(row.get("Notes") or "لا توجد ملاحظات")
        inv_file = row.get("InvoiceFile")

        with st.container(border=True):
            cols = st.columns([2.5, 1.5, 1.5, 2, 1.5])
            with cols[0]:
                st.markdown(f"**المركبة / البند:** {bus_id}")
                st.caption(f"النوع: {v_type}")
            with cols[1]:
                st.markdown(f"**التاريخ:** {done_date}")
                st.caption(f"الحالة: {inv_status}")
            with cols[2]:
                st.markdown(f"**العمل:** {job}")
                st.caption(f"الورشة: {workshop_name}")
            with cols[3]:
                st.markdown(f"**التكلفة:** {money(cost_val)}")
                st.caption(f"ملاحظات: {notes_val}")
            with cols[4]:
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if st.button("✏️", key=f"edit_btn_{log_id}", help="تعديل السجل"):
                        st.session_state[f"editing_log_id"] = log_id
                with btn_cols[1]:
                    if st.button("🗑️", key=f"del_btn_{log_id}", help="حذف السجل"):
                        st.session_state[f"deleting_log_id"] = log_id
                with btn_cols[2]:
                    if inv_file:
                        ui.download_file_button(
                            inv_file,
                            "📄",
                            key=f"dl_inv_{log_id}",
                        )
                    else:
                        st.markdown("—")

        # واجهة التعديل السريع
        if st.session_state.get(f"editing_log_id") == log_id:
            with st.form(f"quick_edit_form_{log_id}"):
                st.markdown(f"##### تعديل السجل رقم #{log_id}")
                f1, f2, f3 = st.columns(3)
                with f1:
                    q_date = st.date_input("التاريخ", value=parse_date(done_date) or today, key=f"q_date_{log_id}")
                    q_job = st.selectbox("نوع العمل", job_types, index=job_types.index(job) if job in job_types else 0, key=f"q_job_{log_id}")
                with f2:
                    q_cost = st.number_input("التكلفة (ريال)", min_value=0.0, value=cost_val, step=50.0, format="%.2f", key=f"q_cost_{log_id}")
                    q_workshop = st.selectbox("الورشة", workshops, index=workshops.index(workshop_name) if workshop_name in workshops else 0, key=f"q_workshop_{log_id}")
                with f3:
                    q_status = st.selectbox("حالة الفاتورة", ["مدفوع", "غير مدفوع"], index=0 if inv_status == "مدفوع" else 1, key=f"q_status_{log_id}")
                    q_file = st.file_uploader("استبدال الفاتورة", type=["pdf", "png", "jpg", "jpeg"], key=f"q_file_{log_id}")
                q_notes = st.text_area("ملاحظات", value=notes_val, key=f"q_notes_{log_id}")

                sub_col1, sub_col2 = st.columns(2)
                with sub_col1:
                    if st.form_submit_button("حفظ التعديلات", type="primary", width="stretch"):
                        try:
                            new_file_path = inv_file
                            if q_file is not None:
                                new_file_path = save_upload("invoices", f"log_{bus_id}", q_file)
                            db.execute(
                                """
                                UPDATE Logs
                                   SET DoneDate=?, JobType=?, Cost=?, Workshop=?,
                                       InvoiceStatus=?, InvoiceFile=?, Notes=?
                                 WHERE LogID=?
                                """,
                                (
                                    str(q_date),
                                    q_job,
                                    float(q_cost),
                                    q_workshop,
                                    q_status,
                                    str(new_file_path or ""),
                                    clean_multiline(q_notes),
                                    log_id,
                                ),
                            )
                            db.log_audit(auth.current_username(), "تعديل", "سجلات الصيانة", log_id, f"{q_job} • {q_cost:,.2f}")
                            st.session_state.pop(f"editing_log_id", None)
                            st.success("تم التعديل بنجاح.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"خطأ: {err}")
                with sub_col2:
                    if st.form_submit_button("إلغاء", width="stretch"):
                        st.session_state.pop(f"editing_log_id", None)
                        st.rerun()

        # واجهة تأكيد الحذف
        if st.session_state.get(f"deleting_log_id") == log_id:
            with st.container(border=True):
                st.warning(f"هل أنت متأكد من رغبتك في حذف السجل رقم #{log_id} نهائياً؟")
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    if st.button("نعم، احذف نهائياً", key=f"confirm_del_{log_id}", type="primary"):
                        if auth.is_admin():
                            db.execute("DELETE FROM Logs WHERE LogID=?", (log_id,))
                            db.log_audit(auth.current_username(), "حذف", "سجلات الصيانة", log_id, f"سجل {bus_id}")
                            st.session_state.pop(f"deleting_log_id", None)
                            st.success("تم الحذف بنجاح.")
                            st.rerun()
                        else:
                            st.error("حذف السجلات متاح لمدير النظام فقط.")
                with d_col2:
                    if st.button("تراجع", key=f"cancel_del_{log_id}"):
                        st.session_state.pop(f"deleting_log_id", None)
                        st.rerun()