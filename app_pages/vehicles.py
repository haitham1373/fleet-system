"""إدارة المركبات: إضافة، تعديل، حذف، عدادات، وصيانة دورية."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core import auth, db, ui
from core.utils import (
    clean_multiline,
    clean_text,
    days_until,
    maintenance_status,
    parse_date,
)

auth.require_login()
ui.page_header(
    "إدارة المركبات",
    "سجل الأسطول والعدادات ومواعيد الصيانة الدورية وتنبيهات الحالة",
    "🚌",
)

vehicle_types = db.fetch_column(
    "SELECT TypeName FROM VehicleTypes ORDER BY TypeName"
)
maintenance_types = db.fetch_column(
    "SELECT JobTypeName FROM MaintenanceTypes ORDER BY JobTypeName"
)

if not maintenance_types:
    maintenance_types = ["صيانة دورية"]


def load_vehicles() -> pd.DataFrame:
    return db.read_df(
        """
        SELECT b.*,
               (SELECT COUNT(*) FROM Logs l WHERE l.BusID = b.BusID) AS LogsCount,
               (SELECT COUNT(*) FROM InspectionReports i2 WHERE i2.BusID = b.BusID)
                   AS InspectionsCount,
               (SELECT COUNT(*) FROM Batteries bt WHERE bt.BusID = b.BusID)
                   AS BatteriesCount
          FROM Buses b
         ORDER BY b.BusID
        """
    )


def compute_maintenance_values(
    odo_current: float,
    odo_last: float,
    oil_validity: int,
    last_date: date,
    days_to_next: int,
) -> tuple[float, str, int, str]:
    km_remaining = float(oil_validity) - max(0.0, float(odo_current) - float(odo_last))
    next_date = last_date + timedelta(days=int(days_to_next))
    days_remaining = (next_date - date.today()).days
    return km_remaining, str(next_date), days_remaining, maintenance_status(days_remaining)


vehicles = load_vehicles()

# ---------------------------------------------------------------------------
# مؤشرات سريعة
# ---------------------------------------------------------------------------
if not vehicles.empty:
    maintenance_days = vehicles["NextDate"].apply(days_until)
    total_vehicles = len(vehicles)
    overdue = int((maintenance_days.notna() & (maintenance_days < 0)).sum())
    urgent = int(
        (
            maintenance_days.notna()
            & (maintenance_days >= 0)
            & (maintenance_days <= 10)
        ).sum()
    )
    alerts = pd.DataFrame(
        {
            "BusID": vehicles["BusID"],
            "VehicleType": vehicles["VehicleType"],
            "NextDate": vehicles["NextDate"],
            "days": maintenance_days,
        }
    )
    alerts = alerts[alerts["days"].notna() & (alerts["days"] <= 30)].sort_values(
        "days"
    )

    columns = st.columns(4)
    columns[0].metric("إجمالي المركبات", f"{total_vehicles:,}")
    columns[1].metric("صيانة متأخرة", f"{overdue:,}")
    columns[2].metric("صيانة عاجلة", f"{urgent:,}")
    columns[3].metric("🔔 تنبيهات الصيانة", f"{len(alerts):,}")

    with st.expander(
        f"🔔 تنبيهات الصيانة — مركبات تحتاج متابعة خلال 30 يوماً ({len(alerts):,})"
    ):
        if alerts.empty:
            ui.empty_state("لا توجد تنبيهات صيانة حالياً.", "✅")
        else:
            alerts_view = alerts.copy()
            alerts_view["أيام متبقية"] = alerts_view["days"].astype(int)
            alerts_view["الحالة"] = alerts_view["days"].apply(maintenance_status)

            def alert_row_class(row: pd.Series) -> str:
                """يحدد لون صف التنبيه حسب حالة الصيانة."""
                status = str(row.get("الحالة") or "")
                if status in {"صيانة متأخرة", "صيانة عاجلة"}:
                    return "row-danger"
                return "row-warning"

            ui.html_table(
                alerts_view,
                columns=[
                    "BusID",
                    "VehicleType",
                    "NextDate",
                    "أيام متبقية",
                    "الحالة",
                ],
                headers={
                    "BusID": "رقم المركبة",
                    "VehicleType": "نوع المركبة",
                    "NextDate": "تاريخ الصيانة القادمة",
                },
                row_class=alert_row_class,
                empty_message="لا توجد تنبيهات صيانة حالياً.",
                max_height="320px",
            )

    st.write("")

# ---------------------------------------------------------------------------
# إضافة مركبة
# ---------------------------------------------------------------------------
with st.expander("➕ إضافة مركبة جديدة"):
    if not vehicle_types:
        st.warning("أضف أنواع المركبات أولاً من صفحة «أنواع المركبات».")
    else:
        with st.form("add_vehicle_form", clear_on_submit=True):
            first, second, third = st.columns(3)

            with first:
                vehicle_type = st.selectbox("نوع المركبة *", vehicle_types)
                bus_id = st.text_input(
                    "رقم المركبة (اللوحة) *", placeholder="مثال: 5486 RXA"
                )
                model = st.text_input("الموديل", placeholder="مثال: 2025")

            with second:
                operation_number = st.text_input(
                    "رقم التشغيل", placeholder="مثال: 101"
                )
                odo_current = st.number_input(
                    "العداد الحالي (كم)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                    format="%.0f",
                )
                odo_last = st.number_input(
                    "العداد السابق (كم)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                    format="%.0f",
                )

            with third:
                oil_validity = st.selectbox(
                    "صلاحية غيار الزيت (كم)",
                    options=[5000, 10000, 15000],
                    index=1,
                )
                maint_type = st.selectbox("نوع الصيانة", maintenance_types)
                last_date = st.date_input("آخر صيانة", value=date.today())
                days_to_next = st.number_input(
                    "أيام حتى الصيانة القادمة",
                    min_value=1,
                    max_value=730,
                    value=30,
                    step=1,
                )

            notes = st.text_area("ملاحظات")

            submitted = st.form_submit_button(
                "حفظ المركبة",
                type="primary",
                width="stretch",
            )

        if submitted:
            bus_id_clean = clean_text(bus_id, 60)
            if not bus_id_clean:
                st.error("رقم المركبة مطلوب.")
            elif odo_last > odo_current:
                st.error("العداد السابق لا يمكن أن يكون أكبر من العداد الحالي.")
            else:
                try:
                    km_remaining, next_date, days_remaining, alert = (
                        compute_maintenance_values(
                            odo_current,
                            odo_last,
                            int(oil_validity),
                            last_date,
                            int(days_to_next),
                        )
                    )
                    db.execute(
                        """
                        INSERT INTO Buses (
                            BusID, VehicleType, Model, OperationNumber,
                            OdoCurrent, OdoLast, KmRemaining, LastDate, NextDate,
                            MaintType, Notes, OilValidity, DaysToMaintenance,
                            AlertStatus, CreatedAt, UpdatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bus_id_clean,
                            vehicle_type,
                            clean_text(model, 80) or "غير متوفر",
                            clean_text(operation_number, 40) or "غير متوفر",
                            float(odo_current),
                            float(odo_last),
                            km_remaining,
                            str(last_date),
                            next_date,
                            maint_type,
                            clean_multiline(notes),
                            int(oil_validity),
                            days_remaining,
                            alert,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
                    db.log_audit(
                        auth.current_username(),
                        "إضافة",
                        "المركبات",
                        bus_id_clean,
                        f"نوع: {vehicle_type}",
                    )
                    st.success("تمت إضافة المركبة بنجاح.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("رقم المركبة هذا مسجل مسبقاً في النظام.")
                except Exception as error:
                    st.error(f"تعذر حفظ المركبة: {error}")

# ---------------------------------------------------------------------------
# تعديل وحذف مركبة
# ---------------------------------------------------------------------------
with st.expander("⚙️ تعديل أو حذف مركبة مسجلة"):
    if vehicles.empty:
        ui.empty_state("لا توجد مركبات مسجلة للتعديل.", "🚌")
    else:
        selection_first, selection_second = st.columns(2)
        available_types = sorted(
            set(vehicles["VehicleType"].dropna().astype(str)) | set(vehicle_types)
        )

        with selection_first:
            edit_type = st.selectbox(
                "تصفية حسب نوع المركبة",
                ["-- الكل --", *available_types],
                key="edit_vehicle_type_filter",
            )

        filtered_ids = (
            vehicles["BusID"].tolist()
            if edit_type == "-- الكل --"
            else vehicles.loc[
                vehicles["VehicleType"] == edit_type, "BusID"
            ].tolist()
        )

        with selection_second:
            selected_bus_id = st.selectbox(
                "اختر رقم المركبة",
                filtered_ids,
                key="edit_vehicle_bus_id",
            )

        selected_vehicle = db.fetch_one(
            "SELECT * FROM Buses WHERE BusID=?", (selected_bus_id,)
        )

        if selected_vehicle:
            current_type = str(selected_vehicle.get("VehicleType") or "")
            type_options = available_types or [current_type or "غير محدد"]
            type_index = (
                type_options.index(current_type)
                if current_type in type_options
                else 0
            )
            current_maint_type = str(selected_vehicle.get("MaintType") or "")
            maint_index = (
                maintenance_types.index(current_maint_type)
                if current_maint_type in maintenance_types
                else 0
            )
            current_oil = int(selected_vehicle.get("OilValidity") or 10000)
            oil_index = (
                [5000, 10000, 15000].index(current_oil)
                if current_oil in (5000, 10000, 15000)
                else 1
            )
            last_date_value = parse_date(selected_vehicle.get("LastDate")) or date.today()
            next_date_value = parse_date(selected_vehicle.get("NextDate"))
            default_days = (
                max(1, (next_date_value - last_date_value).days)
                if next_date_value
                else 30
            )

            with st.form("edit_vehicle_form"):
                first, second, third = st.columns(3)

                with first:
                    edit_vehicle_type = st.selectbox(
                        "نوع المركبة",
                        type_options,
                        index=type_index,
                    )
                    edit_bus_id = st.text_input(
                        "رقم المركبة (اللوحة)",
                        value=selected_bus_id,
                    )
                    edit_model = st.text_input(
                        "الموديل",
                        value=str(selected_vehicle.get("Model") or ""),
                    )

                with second:
                    edit_operation_number = st.text_input(
                        "رقم التشغيل",
                        value=str(selected_vehicle.get("OperationNumber") or ""),
                    )
                    edit_odo_current = st.number_input(
                        "العداد الحالي (كم)",
                        min_value=0.0,
                        step=1.0,
                        value=float(selected_vehicle.get("OdoCurrent") or 0),
                        format="%.0f",
                    )
                    edit_odo_last = st.number_input(
                        "العداد السابق (كم)",
                        min_value=0.0,
                        step=1.0,
                        value=float(selected_vehicle.get("OdoLast") or 0),
                        format="%.0f",
                    )

                with third:
                    edit_oil_validity = st.selectbox(
                        "صلاحية غيار الزيت (كم)",
                        options=[5000, 10000, 15000],
                        index=oil_index,
                    )
                    edit_maint_type = st.selectbox(
                        "نوع الصيانة",
                        maintenance_types,
                        index=maint_index,
                    )
                    edit_last_date = st.date_input(
                        "آخر صيانة",
                        value=last_date_value,
                    )
                    edit_days_to_next = st.number_input(
                        "أيام حتى الصيانة القادمة",
                        min_value=1,
                        max_value=730,
                        value=int(default_days),
                        step=1,
                    )

                edit_notes = st.text_area(
                    "ملاحظات",
                    value=str(selected_vehicle.get("Notes") or ""),
                )

                update_submitted = st.form_submit_button(
                    "حفظ التعديلات",
                    type="primary",
                    width="stretch",
                )

            if update_submitted:
                new_bus_id = clean_text(edit_bus_id, 60)
                if not new_bus_id:
                    st.error("رقم المركبة مطلوب.")
                elif edit_odo_last > edit_odo_current:
                    st.error("العداد السابق لا يمكن أن يكون أكبر من العداد الحالي.")
                else:
                    try:
                        km_remaining, next_date, days_remaining, alert = (
                            compute_maintenance_values(
                                edit_odo_current,
                                edit_odo_last,
                                int(edit_oil_validity),
                                edit_last_date,
                                int(edit_days_to_next),
                            )
                        )
                        with db.get_conn() as connection:
                            connection.execute(
                                """
                                UPDATE Buses
                                   SET BusID=?, VehicleType=?, Model=?,
                                       OperationNumber=?, OdoCurrent=?, OdoLast=?,
                                       KmRemaining=?, LastDate=?, NextDate=?,
                                       MaintType=?, Notes=?, OilValidity=?,
                                       DaysToMaintenance=?, AlertStatus=?,
                                       UpdatedAt=?
                                 WHERE BusID=?
                                """,
                                (
                                    new_bus_id,
                                    edit_vehicle_type,
                                    clean_text(edit_model, 80) or "غير متوفر",
                                    clean_text(edit_operation_number, 40)
                                    or "غير متوفر",
                                    float(edit_odo_current),
                                    float(edit_odo_last),
                                    km_remaining,
                                    str(edit_last_date),
                                    next_date,
                                    edit_maint_type,
                                    clean_multiline(edit_notes),
                                    int(edit_oil_validity),
                                    days_remaining,
                                    alert,
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    selected_bus_id,
                                ),
                            )
                            if new_bus_id != selected_bus_id:
                                connection.execute(
                                    "UPDATE Logs SET BusID=? WHERE BusID=?",
                                    (new_bus_id, selected_bus_id),
                                )
                                connection.execute(
                                    "UPDATE InspectionReports SET BusID=? WHERE BusID=?",
                                    (new_bus_id, selected_bus_id),
                                )
                                connection.execute(
                                    "UPDATE Batteries SET BusID=? WHERE BusID=?",
                                    (new_bus_id, selected_bus_id),
                                )
                                connection.execute(
                                    "UPDATE HotelContracts SET BusID=? WHERE BusID=?",
                                    (new_bus_id, selected_bus_id),
                                )
                                connection.execute(
                                    "UPDATE SmartParkingInvoices SET BusID=? WHERE BusID=?",
                                    (new_bus_id, selected_bus_id),
                                )
                        db.log_audit(
                            auth.current_username(),
                            "تعديل",
                            "المركبات",
                            new_bus_id,
                            "تحديث بيانات المركبة",
                        )
                        st.success("تم تحديث بيانات المركبة بنجاح.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("رقم المركبة الجديد مسجل مسبقاً في النظام.")
                    except Exception as error:
                        st.error(f"تعذر تحديث المركبة: {error}")

            st.divider()
            st.markdown("##### حذف المركبة")
            related_logs = int(
                db.scalar(
                    "SELECT COUNT(*) FROM Logs WHERE BusID=?",
                    (selected_bus_id,),
                    default=0,
                )
                or 0
            )
            related_inspections = int(
                db.scalar(
                    "SELECT COUNT(*) FROM InspectionReports WHERE BusID=?",
                    (selected_bus_id,),
                    default=0,
                )
                or 0
            )
            related_batteries = int(
                db.scalar(
                    "SELECT COUNT(*) FROM Batteries WHERE BusID=?",
                    (selected_bus_id,),
                    default=0,
                )
                or 0
            )
            related_total = related_logs + related_inspections + related_batteries

            if related_total:
                st.warning(
                    "هذه المركبة مرتبطة بـ "
                    f"{related_logs} سجل صيانة، "
                    f"{related_inspections} تقرير فحص، "
                    f"{related_batteries} سجل بطارية."
                )

            confirm_delete = st.checkbox(
                "أؤكد رغبتي في حذف المركبة",
                key="confirm_delete_vehicle",
            )
            cascade_delete = st.checkbox(
                "حذف السجلات المرتبطة أيضاً (صيانة، فحص، بطاريات)",
                key="cascade_delete_vehicle",
            )

            if st.button(
                "حذف المركبة نهائياً",
                type="secondary",
                icon=":material/delete:",
                width="stretch",
            ):
                if not confirm_delete:
                    st.error("يرجى تأكيد الحذف أولاً.")
                elif related_total and not cascade_delete:
                    st.error(
                        "لا يمكن حذف المركبة لوجود سجلات مرتبطة. "
                        "فعّل خيار حذف السجلات المرتبطة أو احتفظ بالمركبة."
                    )
                else:
                    try:
                        with db.get_conn() as connection:
                            if cascade_delete:
                                connection.execute(
                                    "DELETE FROM Logs WHERE BusID=?",
                                    (selected_bus_id,),
                                )
                                connection.execute(
                                    "DELETE FROM InspectionReports WHERE BusID=?",
                                    (selected_bus_id,),
                                )
                                connection.execute(
                                    "DELETE FROM Batteries WHERE BusID=?",
                                    (selected_bus_id,),
                                )
                            connection.execute(
                                "UPDATE HotelContracts SET BusID=NULL WHERE BusID=?",
                                (selected_bus_id,),
                            )
                            connection.execute(
                                "UPDATE SmartParkingInvoices SET BusID=NULL WHERE BusID=?",
                                (selected_bus_id,),
                            )
                            connection.execute(
                                "DELETE FROM Buses WHERE BusID=?",
                                (selected_bus_id,),
                            )
                        db.log_audit(
                            auth.current_username(),
                            "حذف",
                            "المركبات",
                            selected_bus_id,
                            f"حذف السجلات المرتبطة: {cascade_delete}",
                        )
                        st.success("تم حذف المركبة بنجاح.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"تعذر حذف المركبة: {error}")

# ---------------------------------------------------------------------------
# جدول الأسطول
# ---------------------------------------------------------------------------
st.divider()
ui.section_title("جدول الأسطول", "عرض وتصفية جميع المركبات المسجلة")

vehicles = load_vehicles()
if vehicles.empty:
    ui.empty_state("لا توجد مركبات مسجلة حالياً.", "🚌")
else:
    vehicles["أيام الصيانة المتبقية"] = vehicles["NextDate"].apply(days_until)
    vehicles["حالة الصيانة"] = vehicles["أيام الصيانة المتبقية"].apply(
        maintenance_status
    )

    filter_first, filter_second, filter_third = st.columns([1, 1, 1.4])
    filter_types = sorted(
        set(vehicles["VehicleType"].dropna().astype(str)) | set(vehicle_types)
    )
    with filter_first:
        selected_type = st.selectbox(
            "نوع المركبة",
            ["-- الكل --", *filter_types],
            key="fleet_type_filter",
        )
    with filter_second:
        selected_status = st.selectbox(
            "حالة الصيانة",
            [
                "-- الكل --",
                "صيانة متأخرة",
                "صيانة عاجلة",
                "صيانة قادمة",
                "الحالة ممتازة",
                "غير محدد",
            ],
            key="fleet_status_filter",
        )
    with filter_third:
        search_term = st.text_input(
            "بحث برقم المركبة أو الموديل أو رقم التشغيل",
            placeholder="اكتب للبحث...",
        )

    filtered = vehicles.copy()
    if selected_type != "-- الكل --":
        filtered = filtered[filtered["VehicleType"] == selected_type]
    if selected_status != "-- الكل --":
        filtered = filtered[filtered["حالة الصيانة"] == selected_status]
    if search_term.strip():
        term = search_term.strip().lower()
        filtered = filtered[
            filtered["BusID"].astype(str).str.lower().str.contains(term, na=False)
            | filtered["Model"].astype(str).str.lower().str.contains(term, na=False)
            | filtered["OperationNumber"]
            .astype(str)
            .str.lower()
            .str.contains(term, na=False)
        ]

    display = filtered.rename(
        columns={
            "BusID": "رقم المركبة",
            "VehicleType": "نوع المركبة",
            "Model": "الموديل",
            "OperationNumber": "رقم التشغيل",
            "OdoCurrent": "العداد الحالي",
            "OdoLast": "العداد السابق",
            "OilValidity": "صلاحية الزيت (كم)",
            "KmRemaining": "المتبقي (كم)",
            "LastDate": "تاريخ آخر صيانة",
        }
    )

    display_columns = [
        "رقم المركبة",
        "نوع المركبة",
        "الموديل",
        "رقم التشغيل",
        "العداد الحالي",
        "العداد السابق",
        "صلاحية الزيت (كم)",
        "المتبقي (كم)",
        "تاريخ آخر صيانة",
        "أيام الصيانة المتبقية",
        "حالة الصيانة",
    ]

    def fleet_row_class(row: pd.Series) -> str:
        """يحدد صنف CSS للصف حسب حالة الصيانة."""
        status = str(row.get("حالة الصيانة") or "")
        if status in {"صيانة متأخرة", "صيانة عاجلة"}:
            return "row-danger"
        if status == "صيانة قادمة":
            return "row-warning"
        if status == "الحالة ممتازة":
            return "row-ok"
        return "row-muted"

    st.caption(
        "🟥 صيانة متأخرة أو عاجلة   •   🟨 صيانة قادمة   •   "
        "🟩 الحالة ممتازة   •   ⬜ غير محدد"
    )

    ui.html_table(
        display,
        columns=display_columns,
        row_class=fleet_row_class,
        empty_message="لا توجد مركبات مطابقة لخيارات البحث.",
    )

    ui.csv_download_button(
        display[display_columns],
        "fleet_vehicles.csv",
        key="download_fleet_vehicles",
    )