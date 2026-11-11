"""البطاريات والضمان: إدارة بطاريات الأسطول، تواريخ التركيب، الضمان، والمرفقات."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import auth, db, ui
from core.services import bus_id_from_label, bus_labels
from core.utils import (
    clean_multiline,
    parse_date,
    save_upload,
)

auth.require_login()
ui.page_header(
    "البطاريات والضمان",
    "متابعة بطاريات الأسطول، تواريخ التركيب، مدة الضمان، والمرفقات",
    "🔋",
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

batteries = db.read_df(
    """
    SELECT bt.*, bt.rowid AS BatteryID, COALESCE(b.VehicleType, 'غير متوفر') AS VehicleType, b.Model
      FROM Batteries bt
      LEFT JOIN Buses b ON b.BusID = bt.BusID
     ORDER BY COALESCE(bt.InstallDate, '') DESC, bt.rowid DESC
    """
)

today = date.today()
today_ts = pd.Timestamp(today)

if not batteries.empty:
    batteries["_install"] = pd.to_datetime(batteries["InstallDate"], errors="coerce")
    
    def calc_warranty(row):
        inst = pd.to_datetime(row.get("InstallDate"), errors="coerce")
        months = int(row.get("WarrantyMonths") or 12)
        if pd.isna(inst):
            return "غير متوفر", 0, "غير متوفر"
        expiry = inst + pd.DateOffset(months=months)
        rem_days = (expiry - today_ts).days
        if rem_days >= 0:
            return f"🟢 في الضمان (متبقي {rem_days} يوم)", rem_days, "في الضمان"
        else:
            return f"🔴 خارج الضمان (منتهي منذ {abs(rem_days)} يوم)", rem_days, "خارج الضمان"

    res_list = batteries.apply(calc_warranty, axis=1)
    batteries["WarrantyStatusText"] = [r[0] for r in res_list]
    batteries["RemainingDays"] = [r[1] for r in res_list]
    batteries["WarrantyCategory"] = [r[2] for r in res_list]

metric_cols = st.columns(3)
metric_cols[0].metric("إجمالي البطاريات", f"{len(batteries):,}")
metric_cols[1].metric("المركبات المسجلة", f"{len(buses):,}")
metric_cols[2].metric("تاريخ اليوم", str(today))
st.write("")

# ---------------------------------------------------------------------------
# إضافة بطارية جديدة
# ---------------------------------------------------------------------------
with st.expander("➕ تسجيل بطارية جديدة"):
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
        key="bat_vehicle_type_select",
    )

    with st.form("add_battery_form", clear_on_submit=True):
        first, second, third = st.columns(3)

        with first:
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
                    key="bat_bus_label",
                )
            else:
                selected_bus_label = None
                st.warning("لا توجد مركبات مسجلة ضمن النوع المحدد.")

            install_date = st.date_input("تاريخ التركيب", value=today)

        with second:
            battery_type = st.text_input(
                "نوع / ماركة البطارية *",
                placeholder="مثال: اس دلكو، هانكوك...",
            )
            warranty_months = st.number_input(
                "مدة الضمان (بالأشهر)",
                min_value=1,
                value=12,
                step=1,
            )

        with third:
            supplier = st.text_input(
                "الورشة / المورد",
                placeholder="اسم المورد أو مركز الصيانة",
            )
            warranty_file = st.file_uploader(
                "شهادة ضمان البطارية (PDF أو صورة)",
                type=["pdf", "png", "jpg", "jpeg"],
            )

        notes = st.text_area("ملاحظات إضافية")

        submitted = st.form_submit_button(
            "حفظ بيانات البطارية",
            type="primary",
            width="stretch",
        )

    if submitted:
        target_bus_id = bus_id_from_label(selected_bus_label) if selected_bus_label else None
        if not target_bus_id:
            st.error("يرجى اختيار رقم المركبة الصحيح.")
        elif not battery_type.strip():
            st.error("يرجى إدخال نوع/ماركة البطارية.")
        else:
            try:
                stored_file = (
                    save_upload("batteries", f"bat_{target_bus_id}", warranty_file)
                    if warranty_file is not None
                    else ""
                )
                db.execute(
                    """
                    INSERT INTO Batteries (
                        BusID, InstallDate, BatteryType, WarrantyMonths,
                        Supplier, WarrantyFile, Notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_bus_id,
                        str(install_date),
                        battery_type.strip(),
                        int(warranty_months),
                        supplier.strip(),
                        stored_file,
                        clean_multiline(notes),
                    ),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "البطاريات",
                    target_bus_id,
                    f"بطارية: {battery_type} • ضمان {warranty_months} شهر",
                )
                st.success("تم حفظ بيانات البطارية بنجاح.")
                st.rerun()
            except Exception as error:
                st.error(f"تعذر حفظ البطارية: {error}")

# ---------------------------------------------------------------------------
# تصفية البطاريات (تم إضافة فلتر حالة الضمان هنا)
# ---------------------------------------------------------------------------
st.divider()
ui.section_title("تصفية سجلات البطاريات", "ابحث في بطاريات الأسطول")

filter_first, filter_second, filter_third = st.columns(3)
with filter_first:
    type_filter_options = ["-- الكل --", *vehicle_types]
    selected_t_filter = st.selectbox(
        "تصفية حسب نوع المركبة",
        type_filter_options,
        key="bat_type_filter",
    )
with filter_second:
    bus_filter_options = (
        ["-- الكل --", *buses["BusID"].astype(str).tolist()]
        if not buses.empty
        else ["-- الكل --"]
    )
    selected_b_filter = st.selectbox(
        "تصفية حسب رقم المركبة",
        bus_filter_options,
        key="bat_bus_filter",
    )
with filter_third:
    warranty_filter_options = ["-- الكل --", "في الضمان", "خارج الضمان"]
    selected_w_filter = st.selectbox(
        "تصفية حسب حالة الضمان",
        warranty_filter_options,
        key="bat_warranty_filter",
    )

filtered = batteries.copy() if not batteries.empty else batteries
if not filtered.empty:
    if selected_t_filter != "-- الكل --":
        filtered = filtered[filtered["VehicleType"].astype(str) == selected_t_filter]
    if selected_b_filter != "-- الكل --":
        filtered = filtered[filtered["BusID"].astype(str) == selected_b_filter]
    if selected_w_filter != "-- الكل --":
        filtered = filtered[filtered["WarrantyCategory"] == selected_w_filter]

st.caption(f"عدد النتائج: {len(filtered):,} سجل")

# ---------------------------------------------------------------------------
# استعراض وإدارة البطاريات ببطاقات تفاعلية وأزرار مباشرة
# ---------------------------------------------------------------------------
if filtered.empty:
    ui.empty_state("لا توجد سجلات بطاريات مطابقة لخيارات التصفية.", "🔋")
else:
    st.divider()
    ui.section_title("استعراض وإدارة البطاريات", "كل بطارية تضم أزرار التحكم ومستند الضمان الخاص بها مباشرة")

    for _, row in filtered.iterrows():
        battery_id = int(row["BatteryID"])
        bus_id = str(row.get("BusID") or "—")
        v_type = str(row.get("VehicleType") or "—")
        install_d = str(row.get("InstallDate") or "—")
        b_type = str(row.get("BatteryType") or "—")
        w_months = int(row.get("WarrantyMonths") or 12)
        sup = str(row.get("Supplier") or "—")
        notes_val = str(row.get("Notes") or "لا توجد ملاحظات")
        w_status_text = str(row.get("WarrantyStatusText") or "—")
        w_file = row.get("WarrantyFile")

        with st.container(border=True):
            cols = st.columns([2, 1.5, 1.5, 2, 1.5])
            with cols[0]:
                st.markdown(f"**المركبة:** {bus_id}")
                st.caption(f"النوع: {v_type}")
            with cols[1]:
                st.markdown(f"**نوع البطارية:** {b_type}")
                st.caption(f"تاريخ التركيب: {install_d}")
            with cols[2]:
                st.markdown(f"**حالة الضمان:** {w_status_text}")
                st.caption(f"المدة: {w_months} شهر | المورد: {sup}")
            with cols[3]:
                st.markdown(f"**ملاحظات:** {notes_val}")
            with cols[4]:
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if st.button("✏️", key=f"edit_bat_{battery_id}", help="تعديل بيانات البطارية"):
                        st.session_state[f"editing_bat_id"] = battery_id
                with btn_cols[1]:
                    if st.button("🗑️", key=f"del_bat_{battery_id}", help="حذف البطارية"):
                        st.session_state[f"deleting_bat_id"] = battery_id
                with btn_cols[2]:
                    if w_file:
                        ui.download_file_button(
                            w_file,
                            "📄",
                            key=f"dl_bat_file_{battery_id}",
                        )
                    else:
                        st.markdown("—")

        # واجهة التعديل السريع للبطارية
        if st.session_state.get(f"editing_bat_id") == battery_id:
            with st.form(f"edit_bat_form_{battery_id}"):
                st.markdown(f"##### تعديل بيانات البطارية رقم #{battery_id}")
                f1, f2 = st.columns(2)
                with f1:
                    e_install = st.date_input("تاريخ التركيب", value=parse_date(install_d) or today, key=f"e_inst_{battery_id}")
                    e_type = st.text_input("نوع / ماركة البطارية", value=b_type, key=f"e_type_{battery_id}")
                    e_months = st.number_input("مدة الضمان (أشهر)", min_value=1, value=w_months, step=1, key=f"e_mon_{battery_id}")
                with f2:
                    e_sup = st.text_input("الورشة / المورد", value=sup, key=f"e_sup_{battery_id}")
                    e_file = st.file_uploader("استبدال شهادة الضمان", type=["pdf", "png", "jpg", "jpeg"], key=f"e_file_{battery_id}")
                    e_notes = st.text_area("ملاحظات", value=notes_val, key=f"e_notes_{battery_id}")

                sub1, sub2 = st.columns(2)
                with sub1:
                    if st.form_submit_button("حفظ التعديلات", type="primary", width="stretch"):
                        try:
                            final_file = w_file
                            if e_file is not None:
                                final_file = save_upload("batteries", f"bat_{bus_id}", e_file)

                            db.execute(
                                """
                                UPDATE Batteries
                                   SET InstallDate=?, BatteryType=?, WarrantyMonths=?,
                                       Supplier=?, WarrantyFile=?, Notes=?
                                 WHERE rowid=?
                                """,
                                (
                                    str(e_install),
                                    e_type.strip(),
                                    int(e_months),
                                    e_sup.strip(),
                                    str(final_file or ""),
                                    clean_multiline(e_notes),
                                    battery_id,
                                ),
                            )
                            db.log_audit(auth.current_username(), "تعديل", "البطاريات", battery_id, f"تحديث بطارية المركبة {bus_id}")
                            st.session_state.pop(f"editing_bat_id", None)
                            st.success("تم تحديث بيانات البطارية بنجاح.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"خطأ: {err}")
                with sub2:
                    if st.form_submit_button("إلغاء", width="stretch"):
                        st.session_state.pop(f"editing_bat_id", None)
                        st.rerun()

        # واجهة تأكيد الحذف
        if st.session_state.get(f"deleting_bat_id") == battery_id:
            with st.container(border=True):
                st.warning(f"هل أنت متأكد من رغبتك في حذف بطارية المركبة {bus_id} نهائياً؟")
                d_c1, d_c2 = st.columns(2)
                with d_c1:
                    if st.button("نعم، احذف نهائياً", key=f"conf_del_bat_{battery_id}", type="primary"):
                        if auth.is_admin():
                            db.execute("DELETE FROM Batteries WHERE rowid=?", (battery_id,))
                            db.log_audit(auth.current_username(), "حذف", "البطاريات", battery_id, f"بطارية مركبة {bus_id}")
                            st.session_state.pop(f"deleting_bat_id", None)
                            st.success("تم حذف البطارية بنجاح.")
                            st.rerun()
                        else:
                            st.error("حذف البطاريات متاح لمدير النظام فقط.")
                with d_c2:
                    if st.button("تراجع", key=f"canc_del_bat_{battery_id}"):
                        st.session_state.pop(f"deleting_bat_id", None)
                        st.rerun()