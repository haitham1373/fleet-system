"""لوحة التحكم الرئيسية: مؤشرات الأسطول والتنبيهات والحركة الأخيرة."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import auth, db, ui
from core.utils import (
    add_months,
    days_until,
    inspection_status,
    maintenance_status,
    money,
    warranty_status,
)

auth.require_login()
ui.page_header(
    "لوحة التحكم",
    "نظرة شاملة على الأسطول والصيانة والفحص الدوري والضمانات والعقود",
    "📊",
)

buses = db.read_df("SELECT * FROM Buses")
logs = db.read_df("SELECT * FROM Logs")
inspections = db.read_df("SELECT * FROM InspectionReports")
batteries = db.read_df("SELECT * FROM Batteries")
hotel_contracts = db.read_df("SELECT * FROM HotelContracts")
parking_contracts = db.read_df("SELECT * FROM ParkingContracts")
parking_invoices = db.read_df("SELECT * FROM SmartParkingInvoices")

today = date.today()

# ---------------------------------------------------------------------------
# حسابات المؤشرات
# ---------------------------------------------------------------------------
buses["_maintenance_days"] = buses["NextDate"].apply(days_until)
buses["_maintenance_status"] = buses["_maintenance_days"].apply(maintenance_status)
urgent_maintenance = int(
    (buses["_maintenance_days"].notna() & (buses["_maintenance_days"] <= 10)).sum()
)

unpaid_logs = logs[logs["InvoiceStatus"].astype(str).str.strip() == "غير مدفوع"]
unpaid_total = float(unpaid_logs["Cost"].fillna(0).sum()) if not unpaid_logs.empty else 0.0

logs["_date"] = pd.to_datetime(logs["DoneDate"], errors="coerce")
current_month = today.strftime("%Y-%m")
month_cost = (
    float(
        logs.loc[
            logs["_date"].dt.strftime("%Y-%m") == current_month, "Cost"
        ]
        .fillna(0)
        .sum()
    )
    if not logs.empty
    else 0.0
)

if inspections.empty:
    latest_inspections = pd.DataFrame(columns=["BusID", "ExpiryDate", "_days"])
else:
    inspections["_expiry"] = pd.to_datetime(inspections["ExpiryDate"], errors="coerce")
    latest_inspections = (
        inspections.sort_values("_expiry")
        .drop_duplicates(subset=["BusID"], keep="last")
        .copy()
    )
    latest_inspections["_days"] = latest_inspections["ExpiryDate"].apply(days_until)

inspection_alerts = (
    latest_inspections[
        latest_inspections["_days"].notna() & (latest_inspections["_days"] <= 30)
    ]
    if not latest_inspections.empty
    else latest_inspections
)

if batteries.empty:
    latest_batteries = pd.DataFrame(columns=["BusID", "InstallDate", "WarrantyMonths"])
else:
    batteries["_install"] = pd.to_datetime(batteries["InstallDate"], errors="coerce")
    latest_batteries = (
        batteries.sort_values("_install")
        .drop_duplicates(subset=["BusID"], keep="last")
        .copy()
    )
    latest_batteries["_expiry_date"] = latest_batteries.apply(
        lambda row: add_months(
            row["InstallDate"], int(row.get("WarrantyMonths") or 12)
        ),
        axis=1,
    )
    latest_batteries["_days"] = latest_batteries["_expiry_date"].apply(days_until)

battery_alerts = (
    latest_batteries[
        latest_batteries["_days"].notna() & (latest_batteries["_days"] <= 30)
    ]
    if not latest_batteries.empty
    else latest_batteries
)

contracts_frames: list[pd.DataFrame] = []
if not hotel_contracts.empty:
    hotel_view = hotel_contracts.copy()
    hotel_view["نوع العقد"] = "عقد فندق"
    hotel_view["الجهة"] = hotel_view["HotelName"]
    hotel_view["_end"] = hotel_view["EndDate"].apply(days_until)
    contracts_frames.append(hotel_view[["نوع العقد", "الجهة", "EndDate", "_end"]])
if not parking_contracts.empty:
    parking_view = parking_contracts.copy()
    parking_view["نوع العقد"] = "عقد مواقف"
    parking_view["الجهة"] = parking_view["HotelName"].fillna(parking_view["ParkingName"])
    parking_view["_end"] = parking_view["EndDate"].apply(days_until)
    contracts_frames.append(parking_view[["نوع العقد", "الجهة", "EndDate", "_end"]])

contracts = (
    pd.concat(contracts_frames, ignore_index=True) if contracts_frames else pd.DataFrame()
)
contract_alerts = (
    contracts[contracts["_end"].notna() & (contracts["_end"] <= 30)]
    if not contracts.empty
    else contracts
)

# ---------------------------------------------------------------------------
# بطاقات المؤشرات
# ---------------------------------------------------------------------------
metric_row_one = st.columns(4)
metric_row_one[0].metric("إجمالي المركبات", f"{len(buses):,}")
metric_row_one[1].metric("صيانة عاجلة / متأخرة", f"{urgent_maintenance:,}")
metric_row_one[2].metric(
    "فواتير غير مدفوعة",
    f"{len(unpaid_logs):,}",
    delta=money(unpaid_total),
    delta_color="inverse",
)
metric_row_one[3].metric("تكلفة صيانة الشهر", money(month_cost))

metric_row_two = st.columns(4)
metric_row_two[0].metric(
    "فحوصات تحتاج متابعة",
    f"{len(inspection_alerts):,}",
)
metric_row_two[1].metric(
    "ضمانات بطاريات تحتاج متابعة",
    f"{len(battery_alerts):,}",
)
metric_row_two[2].metric(
    "عقود تنتهي خلال 30 يوماً",
    f"{len(contract_alerts):,}",
)
parking_month_total = 0.0
if not parking_invoices.empty:
    parking_invoices["_date"] = pd.to_datetime(
        parking_invoices["ParkingDate"], errors="coerce"
    )
    parking_month_total = float(
        parking_invoices.loc[
            parking_invoices["_date"].dt.strftime("%Y-%m") == current_month, "Cost"
        ]
        .fillna(0)
        .sum()
    )
metric_row_two[3].metric("فواتير المواقف هذا الشهر", money(parking_month_total))

st.write("")

# ---------------------------------------------------------------------------
# التنبيهات
# ---------------------------------------------------------------------------
ui.section_title("التنبيهات التشغيلية", "أهم ما يحتاج متابعة الآن")

maintenance_tab, inspection_tab, battery_tab, contract_tab = st.tabs(
    ["الصيانة", "الفحص الدوري", "ضمان البطاريات", "العقود"]
)

with maintenance_tab:
    maintenance_view = buses[
        buses["_maintenance_days"].notna() & (buses["_maintenance_days"] <= 30)
    ].copy()
    if maintenance_view.empty:
        ui.empty_state("لا توجد صيانة مستحقة خلال 30 يوماً.", "✅")
    else:
        maintenance_view["الحالة"] = maintenance_view["_maintenance_status"]
        maintenance_view["أيام متبقية"] = maintenance_view["_maintenance_days"]
        ui.render_df(
            maintenance_view,
            columns=[
                "BusID",
                "VehicleType",
                "NextDate",
                "أيام متبقية",
                "الحالة",
            ],
            alt="تنبيهات الصيانة",
        )

with inspection_tab:
    if inspection_alerts.empty:
        ui.empty_state("لا توجد فحوصات منتهية أو قريبة الانتهاء.", "✅")
    else:
        inspection_view = inspection_alerts.copy()
        inspection_view["الحالة"] = inspection_view["_days"].apply(inspection_status)
        inspection_view["أيام متبقية"] = inspection_view["_days"]
        ui.render_df(
            inspection_view,
            columns=["BusID", "InspectionDate", "ExpiryDate", "أيام متبقية", "الحالة"],
            alt="تنبيهات الفحص الدوري",
        )

with battery_tab:
    if battery_alerts.empty:
        ui.empty_state("لا توجد ضمانات بطاريات منتهية أو قريبة الانتهاء.", "✅")
    else:
        battery_view = battery_alerts.copy()
        battery_view["الحالة"] = battery_view["_days"].apply(warranty_status)
        battery_view["أيام متبقية"] = battery_view["_days"]
        battery_view["تاريخ الانتهاء"] = battery_view["_expiry_date"]
        ui.render_df(
            battery_view,
            columns=[
                "BusID",
                "BatteryType",
                "تاريخ الانتهاء",
                "أيام متبقية",
                "الحالة",
            ],
            alt="تنبيهات ضمان البطاريات",
        )

with contract_tab:
    if contract_alerts.empty:
        ui.empty_state("لا توجد عقود منتهية أو قريبة الانتهاء.", "✅")
    else:
        contract_view = contract_alerts.copy()
        contract_view["الحالة"] = contract_view["_end"].apply(
            lambda days: "منتهي"
            if days is not None and days < 0
            else ("قريب الانتهاء" if days is not None else "غير محدد")
        )
        contract_view["أيام متبقية"] = contract_view["_end"]
        ui.render_df(
            contract_view,
            columns=["نوع العقد", "الجهة", "EndDate", "أيام متبقية", "الحالة"],
            alt="تنبيهات العقود",
        )

st.write("")

# ---------------------------------------------------------------------------
# الرسم البياني والحركة الأخيرة
# ---------------------------------------------------------------------------
chart_column, recent_column = st.columns([1.35, 1])

with chart_column:
    ui.section_title("تكلفة الصيانة الشهرية", "آخر 6 أشهر")
    if logs.empty:
        ui.empty_state("لا توجد سجلات صيانة لعرض الرسم البياني.", "📈")
    else:
        monthly = logs.dropna(subset=["_date"]).copy()
        if monthly.empty:
            ui.empty_state("لا توجد تواريخ صيانة صالحة لعرض الرسم البياني.", "📈")
        else:
            monthly["الشهر"] = monthly["_date"].dt.to_period("M").astype(str)
            monthly = (
                monthly.groupby("الشهر", as_index=False)["Cost"]
                .sum()
                .rename(columns={"Cost": "التكلفة"})
                .tail(6)
            )
            st.bar_chart(
                monthly,
                x="الشهر",
                y="التكلفة",
                color="#0369a1",
                height=320,
            )

with recent_column:
    ui.section_title("أحدث سجلات الصيانة", "آخر 8 حركات")
    if logs.empty:
        ui.empty_state("لا توجد سجلات صيانة بعد.", "🧾")
    else:
        recent = logs.sort_values("_date", ascending=False).head(8).copy()
        recent["التاريخ"] = recent["DoneDate"]
        recent["التكلفة"] = recent["Cost"].fillna(0).apply(money)
        ui.render_df(
            recent,
            columns=["BusID", "التاريخ", "JobType", "التكلفة", "Workshop"],
            alt="أحدث سجلات الصيانة",
        )
