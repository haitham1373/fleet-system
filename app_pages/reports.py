"""التقرير الشامل: تقرير صيانة الأسطول الشامل المطابق للتنسيق الرسمي."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import auth, db, pdf, ui

auth.require_login()
ui.page_header(
    "التقرير الشامل",
    "استعراض وطباعة تقرير صيانة الأسطول الشامل بتنسيق موحد",
    "📊",
)

# ---------------------------------------------------------------------------
# خيارات التصفية للتقرير الشامل (نفس منطق صفحة السجلات الناجحة)
# ---------------------------------------------------------------------------
vehicle_types = [
    str(value)
    for value in db.fetch_column(
        "SELECT TypeName FROM VehicleTypes ORDER BY TypeName"
    )
]
with st.expander("🔍 خيارات تصفية التقرير الشامل", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("من تاريخ", value=date(2026, 10, 1), key="rep_start_date")
    with col2:
        end_date = st.date_input("إلى تاريخ", value=date.today(), key="rep_end_date")
        
    type_filter = st.selectbox(
        "نوع المركبة / البند",
        ["-- الكل --", "مصروفات عامة", *vehicle_types],
        key="rep_type_filter",
    )
    
    generate_btn = st.button(
        "📄 تجهيز التقرير الشامل للطباعة",
        type="primary",
        width="stretch",
    )

# استعلام جلب البيانات المباشر من جدول Logs الصحيح تماماً مثل صفحة السجلات
logs_query = """
    SELECT l.*, COALESCE(b.VehicleType, 'مصروفات عامة') AS VehicleType,
           b.Model
      FROM Logs l
      LEFT JOIN Buses b ON b.BusID = l.BusID
     ORDER BY COALESCE(l.DoneDate, '') DESC, l.LogID DESC
"""
logs_df = db.read_df(logs_query)

if not logs_df.empty:
    logs_df["_date"] = pd.to_datetime(logs_df["DoneDate"], errors="coerce")
    logs_df["_cost"] = pd.to_numeric(logs_df["Cost"], errors="coerce").fillna(0.0)

if generate_btn:
    filtered_df = logs_df.copy() if not logs_df.empty else logs_df

    # تطبيق فلتر النوع والتاريخ
    if not filtered_df.empty:
        if type_filter == "مصروفات عامة":
            filtered_df = filtered_df[filtered_df["BusID"] == "مصروفات عامة"]
        elif type_filter != "-- الكل --":
            filtered_df = filtered_df[
                filtered_df["VehicleType"].astype(str) == type_filter
            ]

        # فلترة حسب الفترة المحددة
        filtered_df = filtered_df[
            (filtered_df["_date"].dt.date >= start_date)
            & (filtered_df["_date"].dt.date <= end_date)
        ]

    total_fleet_cost = 0.0
    groups: list[dict] = []

    if not filtered_df.empty:
        # تجميع السجلات حسب المركبة أو البند (BusID)
        grouped = filtered_df.groupby(["BusID", "VehicleType"], sort=False)
        for (bus_id, v_type), group in grouped:
            bus_id_str = str(bus_id or "—")
            v_type_str = str(v_type or "مصروفات عامة")
            bus_cost = float(group["_cost"].sum())
            total_fleet_cost += bus_cost

            rows: list[dict] = []
            for _, row in group.iterrows():
                rows.append(
                    {
                        "bus_id": bus_id_str,
                        "date": str(row.get("DoneDate") or "—"),
                        "job": str(row.get("JobType") or "—"),
                        "cost": float(row.get("_cost") or 0.0),
                        "shop": str(row.get("Workshop") or "—"),
                        "status": str(row.get("InvoiceStatus") or "مدفوع"),
                    }
                )

            groups.append(
                {
                    "bus_id": bus_id_str,
                    "vehicle_type": v_type_str,
                    "rows": rows,
                    "total": bus_cost,
                }
            )

    report_bytes = pdf.build_comprehensive_report_pdf(
        start_date=start_date,
        end_date=end_date,
        type_filter=type_filter,
        groups=groups,
        total_cost=total_fleet_cost,
    )

    st.session_state["comprehensive_report_name"] = (
        f"fleet_comprehensive_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    )
    st.session_state["comprehensive_report_bytes"] = report_bytes
    st.session_state["comprehensive_report_ready"] = True
    st.success("تم تجهيز التقرير الشامل بصيغة PDF بنجاح.")

if st.session_state.get("comprehensive_report_ready"):
    st.divider()
    st.download_button(
        "🖨️ تحميل وطباعة التقرير الشامل (PDF)",
        data=st.session_state["comprehensive_report_bytes"],
        file_name=st.session_state["comprehensive_report_name"],
        mime="application/pdf",
        type="primary",
        width="stretch",
        key="download_comprehensive_report",
    )
    st.caption("ملف PDF جاهز للطباعة أو الحفظ على الجهاز.")
