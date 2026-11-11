"""فواتير المواقف الذكية: إضافة، تعديل، حذف، وعرض فواتير المواقف الذكية ومرفقاتها."""

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
    "المواقف الذكية",
    "إدارة وفلترة فواتير المواقف الذكية، المحطات، والمستندات المرفقة",
    "🅿️",
)

buses = db.read_df(
    "SELECT BusID, VehicleType, Model FROM Buses ORDER BY BusID"
)

# جلب فواتير المواقف الذكية مع معرف الصف الفريد rowid باسم ID
invoices = db.read_df(
    """
    SELECT rowid AS ID, HotelName, StationName, BusID, InvoiceDate, Amount,
           InvoiceFile, Notes, CreatedAt, ParkingDate, Cost
      FROM SmartParkingInvoices
     ORDER BY rowid DESC
    """
)

today = date.today()

if not invoices.empty:
    invoices.columns = [str(col).strip() for col in invoices.columns]
    invoice_dates = pd.to_datetime(invoices["InvoiceDate"], errors="coerce")
    if "ParkingDate" in invoices.columns:
        invoice_dates = invoice_dates.fillna(
            pd.to_datetime(invoices["ParkingDate"], errors="coerce")
        )
    invoices["_date"] = invoice_dates
    invoices["_year"] = invoices["_date"].dt.year.fillna(0).astype(int)
    invoices["_month"] = invoices["_date"].dt.month.fillna(0).astype(int)

    invoice_amounts = pd.to_numeric(invoices["Amount"], errors="coerce")
    if "Cost" in invoices.columns:
        invoice_amounts = invoice_amounts.fillna(
            pd.to_numeric(invoices["Cost"], errors="coerce")
        )
    invoices["_amount"] = invoice_amounts.fillna(0.0)

# الإحصائيات العلوية
metric_cols = st.columns(3)
total_inv_count = len(invoices)
total_inv_amount = float(invoices["_amount"].sum()) if not invoices.empty else 0.0

metric_cols[0].metric("إجمالي الفواتير", f"{total_inv_count:,}")
metric_cols[1].metric("إجمالي التكاليف", money(total_inv_amount))
metric_cols[2].metric("تاريخ اليوم", str(today))
st.write("")

# ---------------------------------------------------------------------------
# إضافة فاتورة موقف جديدة
# ---------------------------------------------------------------------------
with st.expander("➕ تسجيل فاتورة موقف جديدة"):
    h_list = [str(x) for x in db.fetch_column("SELECT HotelName FROM Hotels ORDER BY HotelName")]
    s_list = [str(x) for x in db.fetch_column("SELECT StationName FROM Stations ORDER BY StationName")]

    if not h_list:
        st.warning("⚠️ تنبيه: يرجى إضافة فنادق أولاً من صفحة الفنادق والعقود.")
    if not s_list:
        st.warning("⚠️ تنبيه: يرجى إضافة محطات أولاً من صفحة الفنادق والعقود.")

    with st.form("add_parking_invoice_form", clear_on_submit=True):
        first, second, third = st.columns(3)

        with first:
            hotel_name = st.selectbox("اسم الفندق *", h_list if h_list else ["— لا توجد فنادق —"])
            station_name = st.selectbox("اسم المحطة *", s_list if s_list else ["— لا توجد محطات —"])

        with second:
            invoice_date = st.date_input("تاريخ الفاتورة", value=today)
            amount = st.number_input(
                "قيمة الفاتورة (ريال) *",
                min_value=0.0,
                value=500.0,
                step=50.0,
                format="%.2f",
            )

        with third:
            labels = bus_labels()
            bus_options = ["-- بدون مركبة محددة --", *list(labels.values())]
            selected_bus_label = st.selectbox("المركبة المرتبطة (اختياري)", bus_options)
            invoice_file = st.file_uploader(
                "مستند الفاتورة (PDF أو صورة)",
                type=["pdf", "png", "jpg", "jpeg"],
            )

        notes = st.text_area("ملاحظات إضافية")

        submitted = st.form_submit_button(
            "حفظ الفاتورة",
            type="primary",
            width="stretch",
        )

    if submitted:
        if not h_list or not s_list:
            st.error("لا يمكن حفظ الفاتورة لعدم وجود فنادق أو محطات مسجلة.")
        else:
            target_bus_id = (
                bus_id_from_label(selected_bus_label)
                if selected_bus_label != "-- بدون مركبة محددة --"
                else "None"
            )

            try:
                stored_file = (
                    save_upload("parking_invoices", f"park_{hotel_name}", invoice_file)
                    if invoice_file is not None
                    else ""
                )
                
                db.execute(
                    """
                    INSERT INTO SmartParkingInvoices (
                        HotelName, StationName, BusID, InvoiceDate, Amount,
                        InvoiceFile, Notes, CreatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hotel_name,
                        station_name,
                        target_bus_id,
                        str(invoice_date),
                        float(amount),
                        stored_file,
                        clean_multiline(notes),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                db.log_audit(
                    auth.current_username(),
                    "إضافة",
                    "المواقف الذكية",
                    hotel_name,
                    f"قيمة الفاتورة: {amount:,.2f} ريال",
                )
                st.success("تم حفظ فاتورة الموقف بنجاح.")
                st.rerun()
            except Exception as error:
                st.error(f"تعذر حفظ الفاتورة: {error}")

# ---------------------------------------------------------------------------
# تصفية الفواتير
# ---------------------------------------------------------------------------
st.divider()
ui.section_title("تصفية فواتير المواقف المسجلة", "بحث دقيق حسب الفندق، المحطة، السنة، والشهر")

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    h_vals = invoices["HotelName"].dropna().unique().tolist() if not invoices.empty and "HotelName" in invoices else []
    hotel_options = ["-- الكل --", *sorted(h_vals)]
    selected_hotel_filter = st.selectbox(
        "تصفية حسب الفندق",
        hotel_options,
        key="park_hotel_filter",
    )

with filter_col2:
    s_vals = invoices["StationName"].dropna().unique().tolist() if not invoices.empty and "StationName" in invoices else []
    station_options = ["-- الكل --", *sorted(s_vals)]
    selected_station_filter = st.selectbox(
        "تصفية حسب المحطة",
        station_options,
        key="park_station_filter",
    )

with filter_col3:
    y_vals = sorted([str(y) for y in invoices["_year"].unique() if y > 0]) if not invoices.empty else []
    year_options = ["-- الكل --", *y_vals]
    selected_year_filter = st.selectbox(
        "تصفية حسب السنة",
        year_options,
        key="park_year_filter",
    )

filtered = invoices.copy() if not invoices.empty else invoices
if not filtered.empty:
    if selected_hotel_filter != "-- الكل --" and "HotelName" in filtered:
        filtered = filtered[filtered["HotelName"] == selected_hotel_filter]
    if selected_station_filter != "-- الكل --" and "StationName" in filtered:
        filtered = filtered[filtered["StationName"] == selected_station_filter]
    if selected_year_filter != "-- الكل --":
        filtered = filtered[filtered["_year"] == int(selected_year_filter)]

st.caption(f"عدد النتائج: {len(filtered):,} فاتورة")

# ---------------------------------------------------------------------------
# استعراض وإدارة فواتير المواقف ببطاقات تفاعلية وأزرار مباشرة
# ---------------------------------------------------------------------------
if filtered.empty:
    ui.empty_state("لا توجد فواتير مواقف مطابقة لخيارات التصفية.", "🅿️")
else:
    st.divider()
    ui.section_title("استعراض وإدارة فواتير المواقف", "كل فاتورة تضم أزرار التحكم ومستند الموقف الخاص بها مباشرة")

    for _, row in filtered.iterrows():
        invoice_id = int(row["ID"])
        hotel_n = str(row.get("HotelName", "—"))
        station_n = str(row.get("StationName", "—"))
        bus_val = str(row.get("BusID", "—"))
        if bus_val.strip().lower() in {"none", "nan", "", "—"}:
            bus_val = "بدون مركبة"
        inv_date = str(row.get("InvoiceDate", "—"))

        amount_val = to_float(row.get("_amount"), to_float(row.get("Amount"), 0.0))

        notes_val = str(row.get("Notes", "لا توجد ملاحظات"))
        invoice_file = row.get("InvoiceFile", None)

        with st.container(border=True):
            cols = st.columns([2, 1.5, 1.5, 2, 1.5])
            with cols[0]:
                st.markdown(f"**الفندق:** {hotel_n}")
                st.caption(f"المحطة: {station_n}")
            with cols[1]:
                st.markdown(f"**التاريخ:** {inv_date}")
                st.caption(f"المركبة: {bus_val}")
            with cols[2]:
                st.markdown(f"**القيمة:** {money(amount_val)}")
            with cols[3]:
                st.markdown(f"**ملاحظات:** {notes_val}")
            with cols[4]:
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if st.button("✏️", key=f"edit_park_{invoice_id}", help="تعديل الفاتورة"):
                        st.session_state[f"editing_park_id"] = invoice_id
                with btn_cols[1]:
                    if st.button("🗑️", key=f"del_park_{invoice_id}", help="حذف الفاتورة"):
                        st.session_state[f"deleting_park_id"] = invoice_id
                with btn_cols[2]:
                    if invoice_file:
                        ui.download_file_button(
                            invoice_file,
                            "📄",
                            key=f"dl_park_file_{invoice_id}",
                        )
                    else:
                        st.markdown("—")

        # واجهة التعديل السريع للفاتورة
        if st.session_state.get(f"editing_park_id") == invoice_id:
            with st.form(f"edit_park_form_{invoice_id}"):
                st.markdown(f"##### تعديل الفاتورة رقم #{invoice_id}")
                f1, f2, f3 = st.columns(3)
                with f1:
                    e_hotel = st.selectbox("اسم الفندق", h_list if h_list else [hotel_n], index=h_list.index(hotel_n) if hotel_n in h_list else 0, key=f"e_park_hotel_{invoice_id}")
                    e_station = st.selectbox("اسم المحطة", s_list if s_list else [station_n], index=s_list.index(station_n) if station_n in s_list else 0, key=f"e_park_station_{invoice_id}")
                with f2:
                    e_date = st.date_input("تاريخ الفاتورة", value=parse_date(inv_date) or today, key=f"e_park_date_{invoice_id}")
                    e_amount = st.number_input("قيمة الفاتورة (ريال)", min_value=0.0, value=amount_val, step=50.0, format="%.2f", key=f"e_park_amt_{invoice_id}")
                with f3:
                    e_file = st.file_uploader("استبدال مستند الفاتورة", type=["pdf", "png", "jpg", "jpeg"], key=f"e_park_file_{invoice_id}")
                    e_notes = st.text_area("ملاحظات", value=notes_val, key=f"e_park_notes_{invoice_id}")

                sub1, sub2 = st.columns(2)
                with sub1:
                    if st.form_submit_button("حفظ التعديلات", type="primary", width="stretch"):
                        try:
                            final_file = invoice_file
                            if e_file is not None:
                                final_file = save_upload("parking_invoices", f"park_{e_hotel}", e_file)

                            db.execute(
                                """
                                UPDATE SmartParkingInvoices
                                   SET HotelName = ?, 
                                       StationName = ?, 
                                       InvoiceDate = ?, 
                                       Amount = ?,
                                       InvoiceFile = ?, 
                                       Notes = ?
                                 WHERE rowid = ?
                                """,
                                (
                                    e_hotel.strip(),
                                    e_station.strip(),
                                    str(e_date),
                                    float(e_amount),
                                    str(final_file or ""),
                                    clean_multiline(e_notes),
                                    invoice_id,
                                ),
                            )
                            db.log_audit(auth.current_username(), "تعديل", "المواقف الذكية", invoice_id, f"تحديث فاتورة فندق {e_hotel}")
                            st.session_state.pop(f"editing_park_id", None)
                            st.success("تم تحديث الفاتورة بنجاح.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"خطأ: {err}")
                with sub2:
                    if st.form_submit_button("إلغاء", width="stretch"):
                        st.session_state.pop(f"editing_park_id", None)
                        st.rerun()

        # واجهة تأكيد الحذف
        if st.session_state.get(f"deleting_park_id") == invoice_id:
            with st.container(border=True):
                st.warning(f"هل أنت متأكد من رغبتك في حذف فاتورة فندق ({hotel_n}) نهائياً؟")
                d_c1, d_c2 = st.columns(2)
                with d_c1:
                    if st.button("نعم، احذف نهائياً", key=f"conf_del_park_{invoice_id}", type="primary"):
                        db.execute("DELETE FROM SmartParkingInvoices WHERE rowid = ?", (invoice_id,))
                        db.log_audit(auth.current_username(), "حذف", "المواقف الذكية", invoice_id, f"فاتورة فندق {hotel_n}")
                        st.session_state.pop(f"deleting_park_id", None)
                        st.success("تم حذف الفاتورة بنجاح.")
                        st.rerun()
                with d_c2:
                    if st.button("تراجع", key=f"canc_del_park_{invoice_id}"):
                        st.session_state.pop(f"deleting_park_id", None)
                        st.rerun()