"""الفنادق والعقود: إدارة الفنادق، المحطات، والعقود بالبطاقات التفاعلية والفلاتر الدقيقة."""

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
)

auth.require_login()
ui.page_header(
    "الفنادق والعقود",
    "إدارة الفنادق، المحطات، عقود الإسكان، والمستندات المرفقة",
    "🏨",
)

# التأكد من إنشاء الجداول والأعمدة الأساسية لمنع أي خطأ نهائياً
db.execute("""
    CREATE TABLE IF NOT EXISTS Hotels (
        HotelName TEXT UNIQUE,
        Notes TEXT,
        CreatedAt TEXT
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS Stations (
        StationName TEXT UNIQUE,
        Notes TEXT,
        CreatedAt TEXT
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS HotelContracts (
        HotelName TEXT,
        StationName TEXT,
        BusID TEXT,
        StartDate TEXT,
        EndDate TEXT,
        Amount REAL,
        ContractFile TEXT,
        Notes TEXT,
        CreatedAt TEXT
    )
""")

# التأكد من وجود عمود Amount في جدول العقود القديم إن وجد
try:
    db.execute("ALTER TABLE HotelContracts ADD COLUMN Amount REAL")
except Exception:
    pass

buses = db.read_df(
    "SELECT BusID, VehicleType, Model FROM Buses ORDER BY BusID"
)

# ---------------------------------------------------------------------------
# 1. إدارة الفنادق والمنشآت (إضافة، تعديل، حذف)
# ---------------------------------------------------------------------------
with st.expander("🏨 إدارة الفنادق والمنشآت (إضافة / تعديل / حذف)"):
    tab_add_hotel, tab_edit_hotel = st.tabs(["➕ إضافة فندق", "⚙️ تعديل أو حذف فندق"])
    
    with tab_add_hotel:
        with st.form("add_hotel_form", clear_on_submit=True):
            new_hotel_name = st.text_input("اسم الفندق / المنشأة *", placeholder="مثال: فندق تاج بارك")
            hotel_notes = st.text_area("ملاحظات الفندق")
            h_submitted = st.form_submit_button("حفظ الفندق", type="primary", width="stretch")
            
            if h_submitted:
                if not new_hotel_name.strip():
                    st.error("اسم الفندق مطلوب.")
                else:
                    try:
                        db.execute(
                            "INSERT INTO Hotels (HotelName, Notes, CreatedAt) VALUES (?, ?, ?)",
                            (new_hotel_name.strip(), clean_multiline(hotel_notes), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        )
                        db.log_audit(auth.current_username(), "إضافة", "الفنادق", new_hotel_name, "إضافة فندق جديد")
                        st.success("تم إضافة الفندق بنجاح.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"تعذر الحفظ (ربما الاسم موجود مسبقاً): {e}")

    with tab_edit_hotel:
        hotels_df = db.read_df("SELECT rowid as HotelID, HotelName, Notes FROM Hotels ORDER BY HotelName")
        if hotels_df.empty:
            st.info("لا توجد فنادق مسجلة حالياً.")
        else:
            hotel_opts = {row["HotelName"]: row for _, row in hotels_df.iterrows()}
            selected_h_name = st.selectbox("اختر الفندق للتعامل معه", list(hotel_opts.keys()), key="sel_hotel_edit")
            h_row = hotel_opts[selected_h_name]
            h_id = int(h_row["HotelID"])
            
            with st.form(f"edit_hotel_form_{h_id}"):
                up_h_name = st.text_input("تعديل اسم الفندق", value=str(h_row["HotelName"]))
                up_h_notes = st.text_area("تعديل الملاحظات", value=str(h_row["Notes"] or ""))
                up_h_sub = st.form_submit_button("حفظ التعديلات", type="primary", width="stretch")
                
                if up_h_sub:
                    try:
                        db.execute("UPDATE Hotels SET HotelName=?, Notes=? WHERE rowid=?", (up_h_name.strip(), clean_multiline(up_h_notes), h_id))
                        db.log_audit(auth.current_username(), "تعديل", "الفنادق", h_id, f"تعديل إلى: {up_h_name}")
                        st.success("تم تحديث الفندق بنجاح.")
                        st.rerun()
                    except Exception as err:
                        st.error(f"خطأ: {err}")
            
            if auth.is_admin():
                if st.button("حذف هذا الفندق نهائياً", key=f"del_hotel_{h_id}", type="secondary"):
                    db.execute("DELETE FROM Hotels WHERE rowid=?", (h_id,))
                    db.log_audit(auth.current_username(), "حذف", "الفنادق", h_id, selected_h_name)
                    st.success("تم حذف الفندق.")
                    st.rerun()

# ---------------------------------------------------------------------------
# 2. إدارة المحطات (إضافة، تعديل، حذف)
# ---------------------------------------------------------------------------
with st.expander("🚉 إدارة المحطات (إضافة / تعديل / حذف)"):
    tab_add_st, tab_edit_st = st.tabs(["➕ إضافة محطة", "⚙️ تعديل أو حذف محطة"])
    
    with tab_add_st:
        with st.form("add_station_form", clear_on_submit=True):
            new_st_name = st.text_input("اسم المحطة *", placeholder="مثال: محطة جبل الكعبة الغربي")
            st_notes = st.text_area("ملاحظات المحطة")
            st_submitted = st.form_submit_button("حفظ المحطة", type="primary", width="stretch")
            
            if st_submitted:
                if not new_st_name.strip():
                    st.error("اسم المحطة مطلوب.")
                else:
                    try:
                        db.execute(
                            "INSERT INTO Stations (StationName, Notes, CreatedAt) VALUES (?, ?, ?)",
                            (new_st_name.strip(), clean_multiline(st_notes), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        )
                        db.log_audit(auth.current_username(), "إضافة", "المحطات", new_st_name, "إضافة محطة جديدة")
                        st.success("تم إضافة المحطة بنجاح.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"تعذر الحفظ (ربما الاسم موجود مسبقاً): {e}")

    with tab_edit_st:
        stations_df = db.read_df("SELECT rowid as StationID, StationName, Notes FROM Stations ORDER BY StationName")
        if stations_df.empty:
            st.info("لا توجد محطات مسجلة حالياً.")
        else:
            station_opts = {row["StationName"]: row for _, row in stations_df.iterrows()}
            selected_st_name = st.selectbox("اختر المحطة للتعامل معها", list(station_opts.keys()), key="sel_station_edit")
            st_row = station_opts[selected_st_name]
            st_id = int(st_row["StationID"])
            
            with st.form(f"edit_station_form_{st_id}"):
                up_st_name = st.text_input("تعديل اسم المحطة", value=str(st_row["StationName"]))
                up_st_notes = st.text_area("تعديل الملاحظات", value=str(st_row["Notes"] or ""))
                up_st_sub = st.form_submit_button("حفظ التعديلات", type="primary", width="stretch")
                
                if up_st_sub:
                    try:
                        db.execute("UPDATE Stations SET StationName=?, Notes=? WHERE rowid=?", (up_st_name.strip(), clean_multiline(up_st_notes), st_id))
                        db.log_audit(auth.current_username(), "تعديل", "المحطات", st_id, f"تعديل إلى: {up_st_name}")
                        st.success("تم تحديث المحطة بنجاح.")
                        st.rerun()
                    except Exception as err:
                        st.error(f"خطأ: {err}")
            
            if auth.is_admin():
                if st.button("حذف هذه المحطة نهائياً", key=f"del_station_{st_id}", type="secondary"):
                    db.execute("DELETE FROM Stations WHERE rowid=?", (st_id,))
                    db.log_audit(auth.current_username(), "حذف", "المحطات", st_id, selected_st_name)
                    st.success("تم حذف المحطة.")
                    st.rerun()

# ---------------------------------------------------------------------------
# 3. عقود الفنادق والإسكان
# ---------------------------------------------------------------------------
# استخدام rowid صريح وموحد باسم ID لضمان عمل أزرار التعديل والحذف بشكل مضمون
contracts = db.read_df(
    """
    SELECT rowid AS ID, HotelName, StationName, BusID, StartDate, EndDate, Amount, ContractFile, Notes, CreatedAt
      FROM HotelContracts
     ORDER BY rowid DESC
    """
)

today = date.today()
today_ts = pd.Timestamp(today)

if not contracts.empty:
    contracts.columns = [str(col).strip() for col in contracts.columns]
    
    contracts["_start"] = pd.to_datetime(contracts["StartDate"], errors="coerce") if "StartDate" in contracts else pd.NaT
    contracts["_end"] = pd.to_datetime(contracts["EndDate"], errors="coerce") if "EndDate" in contracts else pd.NaT
    
    contracts["_start_year"] = contracts["_start"].dt.year.fillna(0).astype(int)
    contracts["_start_month"] = contracts["_start"].dt.month.fillna(0).astype(int)

    def calc_contract_status(row):
        end_dt = row["_end"]
        if pd.isna(end_dt):
            return "ساري", 0
        rem = (end_dt - today_ts).days
        if rem >= 0:
            return "ساري", rem
        else:
            return "منتهي", rem

    res_list = contracts.apply(calc_contract_status, axis=1)
    contracts["ContractStatus"] = [r[0] for r in res_list]
    contracts["RemainingDays"] = [r[1] for r in res_list]

metric_cols = st.columns(3)
metric_cols[0].metric("إجمالي العقود", f"{len(contracts):,}")
active_contracts = contracts[contracts["ContractStatus"] == "ساري"] if not contracts.empty else contracts
metric_cols[1].metric("العقود السارية", f"{len(active_contracts):,}")

total_val = 0.0
if not contracts.empty and "Amount" in contracts.columns:
    total_val = pd.to_numeric(contracts["Amount"], errors="coerce").fillna(0.0).sum()
metric_cols[2].metric("إجمالي قيم العقود", money(total_val))
st.write("")

# إضافة عقد جديد
with st.expander("➕ إضافة عقد فندق جديد"):
    h_list = [str(x) for x in db.fetch_column("SELECT HotelName FROM Hotels ORDER BY HotelName")]
    s_list = [str(x) for x in db.fetch_column("SELECT StationName FROM Stations ORDER BY StationName")]

    if not h_list:
        st.warning("⚠️ تنبيه: يرجى إضافة فنادق أولاً من قسم 'إدارة الفنادق والمنشآت' بالأعلى.")
    if not s_list:
        st.warning("⚠️ تنبيه: يرجى إضافة محطات أولاً من قسم 'إدارة المحطات' بالأعلى.")

    with st.form("add_contract_form", clear_on_submit=True):
        first, second, third = st.columns(3)

        with first:
            hotel_name = st.selectbox("اسم الفندق *", h_list if h_list else ["— لا توجد فنادق —"])
            station_name = st.selectbox("المحطة *", s_list if s_list else ["— لا توجد محطات —"])
            
            labels = bus_labels()
            bus_options = ["-- بدون مركبة محددة --", *list(labels.values())]
            selected_bus_label = st.selectbox("المركبة المرتبطة (اختياري)", bus_options)

        with second:
            start_date = st.date_input("بداية العقد", value=today)
            end_date = st.date_input("نهاية العقد", value=today)
            amount = st.number_input(
                "قيمة العقد (ريال) *",
                min_value=0.0,
                value=5000.0,
                step=500.0,
                format="%.2f",
            )

        with third:
            contract_file = st.file_uploader(
                "مستند العقد (PDF أو صورة)",
                type=["pdf", "png", "jpg", "jpeg"],
            )
            notes = st.text_area("ملاحظات إضافية")

        submitted = st.form_submit_button(
            "حفظ العقد",
            type="primary",
            width="stretch",
        )

    if submitted:
        if not h_list or not s_list:
            st.error("لا يمكن حفظ العقد لعدم وجود فنادق أو محطات مسجلة.")
        else:
            target_bus_id = (
                bus_id_from_label(selected_bus_label)
                if selected_bus_label != "-- بدون مركبة محددة --"
                else "None"
            )

            if end_date < start_date:
                st.error("تاريخ نهاية العقد لا يمكن أن يكون قبل تاريخ البداية.")
            else:
                try:
                    stored_file = (
                        save_upload("contracts", f"contract_{hotel_name}", contract_file)
                        if contract_file is not None
                        else ""
                    )
                    
                    db.execute(
                        """
                        INSERT INTO HotelContracts (
                            HotelName, StationName, BusID, StartDate, EndDate,
                            Amount, ContractFile, Notes, CreatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            hotel_name,
                            station_name,
                            target_bus_id,
                            str(start_date),
                            str(end_date),
                            float(amount),
                            stored_file,
                            clean_multiline(notes),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
                    db.log_audit(
                        auth.current_username(),
                        "إضافة",
                        "عقود الفنادق",
                        hotel_name,
                        f"قيمة العقد: {amount:,.2f} ريال",
                    )
                    st.success("تم حفظ العقد بنجاح.")
                    st.rerun()
                except Exception as error:
                    st.error(f"تعذر حفظ العقد: {error}")

# تصفية العقود
st.divider()
ui.section_title("تصفية العقود المسجلة", "بحث دقيق حسب الفندق، السنة، والشهر")

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    h_vals = contracts["HotelName"].dropna().unique().tolist() if not contracts.empty and "HotelName" in contracts else []
    hotel_options = ["-- الكل --", *sorted(h_vals)]
    selected_hotel_filter = st.selectbox(
        "تصفية حسب الفندق",
        hotel_options,
        key="contract_hotel_filter",
    )

with filter_col2:
    y_vals = sorted([str(y) for y in contracts["_start_year"].unique() if y > 0]) if not contracts.empty else []
    year_options = ["-- الكل --", *y_vals]
    selected_year_filter = st.selectbox(
        "تصفية حسب السنة",
        year_options,
        key="contract_year_filter",
    )

with filter_col3:
    month_names = {
        1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
        5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
        9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
    }
    month_options = ["-- الكل --", *[month_names[m] for m in range(1, 13)]]
    selected_month_filter = st.selectbox(
        "تصفية حسب الشهر",
        month_options,
        key="contract_month_filter",
    )

filtered = contracts.copy() if not contracts.empty else contracts
if not filtered.empty:
    if selected_hotel_filter != "-- الكل --" and "HotelName" in filtered:
        filtered = filtered[filtered["HotelName"] == selected_hotel_filter]
    
    if selected_year_filter != "-- الكل --":
        filtered = filtered[filtered["_start_year"] == int(selected_year_filter)]
        
    if selected_month_filter != "-- الكل --":
        inv_month_names = {v: k for k, v in month_names.items()}
        m_num = inv_month_names.get(selected_month_filter)
        if m_num:
            filtered = filtered[filtered["_start_month"] == m_num]

st.caption(f"عدد النتائج: {len(filtered):,} عقد")

# استعراض وإدارة العقود
if filtered.empty:
    ui.empty_state("لا توجد عقود مطابقة لخيارات التصفية.", "🏨")
else:
    st.divider()
    ui.section_title("استعراض وإدارة العقود", "كل عقد يضم أزرار التحكم ومستند العقد الخاص به مباشرة")

    for _, row in filtered.iterrows():
        contract_id = int(row["ID"])
        hotel_n = str(row.get("HotelName", "—"))
        station_n = str(row.get("StationName", "—"))
        bus_val = str(row.get("BusID", "—"))
        start_d = str(row.get("StartDate", "—"))
        end_d = str(row.get("EndDate", "—"))
        
        raw_amt = row.get("Amount", 0.0)
        try:
            amount_val = float(raw_amt) if raw_amt is not None else 0.0
        except (ValueError, TypeError):
            amount_val = 0.0

        status_val = str(row.get("ContractStatus", "ساري"))
        rem_d = int(row.get("RemainingDays", 0))
        notes_val = str(row.get("Notes", "لا توجد ملاحظات"))
        contract_file = row.get("ContractFile", None)

        status_display = f"🟢 ساري (متبقي {rem_d} يوم)" if status_val == "ساري" else f"🔴 منتهي (منذ {abs(rem_d)} يوم)"

        with st.container(border=True):
            cols = st.columns([2, 1.5, 1.5, 2, 1.5])
            with cols[0]:
                st.markdown(f"**الفندق:** {hotel_n}")
                st.caption(f"المحطة: {station_n}")
            with cols[1]:
                st.markdown(f"**الفترة:** من {start_d}")
                st.caption(f"إلى: {end_d}")
            with cols[2]:
                st.markdown(f"**القيمة:** {money(amount_val)}")
                st.caption(f"الحالة: {status_display}")
            with cols[3]:
                st.markdown(f"**ملاحظات:** {notes_val}")
                st.caption(f"المركبة: {bus_val}")
            with cols[4]:
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if st.button("✏️", key=f"edit_contract_{contract_id}", help="تعديل العقد"):
                        st.session_state[f"editing_contract_id"] = contract_id
                with btn_cols[1]:
                    if st.button("🗑️", key=f"del_contract_{contract_id}", help="حذف العقد"):
                        st.session_state[f"deleting_contract_id"] = contract_id
                with btn_cols[2]:
                    if contract_file:
                        ui.download_file_button(
                            contract_file,
                            "📄",
                            key=f"dl_contract_file_{contract_id}",
                        )
                    else:
                        st.markdown("—")

        # واجهة التعديل السريع للعقد
        if st.session_state.get(f"editing_contract_id") == contract_id:
            with st.form(f"edit_contract_form_{contract_id}"):
                st.markdown(f"##### تعديل بيانات العقد رقم #{contract_id}")
                f1, f2, f3 = st.columns(3)
                with f1:
                    e_hotel = st.selectbox("اسم الفندق", h_list if h_list else [hotel_n], index=h_list.index(hotel_n) if hotel_n in h_list else 0, key=f"e_hotel_{contract_id}")
                    e_station = st.selectbox("المحطة", s_list if s_list else [station_n], index=s_list.index(station_n) if station_n in s_list else 0, key=f"e_station_{contract_id}")
                with f2:
                    e_start = st.date_input("بداية العقد", value=parse_date(start_d) or today, key=f"e_start_{contract_id}")
                    e_end = st.date_input("نهاية العقد", value=parse_date(end_d) or today, key=f"e_end_{contract_id}")
                with f3:
                    e_amount = st.number_input("قيمة العقد (ريال)", min_value=0.0, value=amount_val, step=500.0, format="%.2f", key=f"e_amt_{contract_id}")
                    e_file = st.file_uploader("استبدال مستند العقد", type=["pdf", "png", "jpg", "jpeg"], key=f"e_file_{contract_id}")
                
                e_notes = st.text_area("ملاحظات", value=notes_val, key=f"e_notes_{contract_id}")

                sub1, sub2 = st.columns(2)
                with sub1:
                    if st.form_submit_button("حفظ التعديلات", type="primary", width="stretch"):
                        try:
                            final_file = contract_file
                            if e_file is not None:
                                final_file = save_upload("contracts", f"contract_{e_hotel}", e_file)

                            db.execute(
                                """
                                UPDATE HotelContracts
                                   SET HotelName = ?, 
                                       StationName = ?, 
                                       StartDate = ?, 
                                       EndDate = ?,
                                       Amount = ?, 
                                       ContractFile = ?, 
                                       Notes = ?
                                 WHERE rowid = ?
                                """,
                                (
                                    e_hotel.strip(),
                                    e_station.strip(),
                                    str(e_start),
                                    str(e_end),
                                    float(e_amount),
                                    str(final_file or ""),
                                    clean_multiline(e_notes),
                                    contract_id,
                                ),
                            )
                            db.log_audit(auth.current_username(), "تعديل", "عقود الفنادق", contract_id, f"تحديث عقد فندق {e_hotel}")
                            st.session_state.pop(f"editing_contract_id", None)
                            st.success("تم تحديث العقد بنجاح.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"خطأ: {err}")
                with sub2:
                    if st.form_submit_button("إلغاء", width="stretch"):
                        st.session_state.pop(f"editing_contract_id", None)
                        st.rerun()

        # واجهة تأكيد الحذف
        if st.session_state.get(f"deleting_contract_id") == contract_id:
            with st.container(border=True):
                st.warning(f"هل أنت متأكد من رغبتك في حذف عقد فندق ({hotel_n}) نهائياً؟")
                d_c1, d_c2 = st.columns(2)
                with d_c1:
                    if st.button("نعم، احذف نهائياً", key=f"conf_del_contract_{contract_id}", type="primary"):
                        if auth.is_admin():
                            db.execute("DELETE FROM HotelContracts WHERE rowid = ?", (contract_id,))
                            db.log_audit(auth.current_username(), "حذف", "عقود الفنادق", contract_id, f"عقد فندق {hotel_n}")
                            st.session_state.pop(f"deleting_contract_id", None)
                            st.success("تم حذف العقد بنجاح.")
                            st.rerun()
                        else:
                            st.error("حذف العقود متاح لمدير النظام فقط.")
                with d_c2:
                    if st.button("تراجع", key=f"canc_del_contract_{contract_id}"):
                        st.session_state.pop(f"deleting_contract_id", None)
                        st.rerun()