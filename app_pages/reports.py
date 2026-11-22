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
        start_date = st.date_input(
            "من تاريخ",
            value=date(date.today().year, 1, 1),
            key="rep_start_date",
        )
    with col2:
        end_date = st.date_input("إلى تاريخ", value=date.today(), key="rep_end_date")
        
    type_filter = st.multiselect(
        "نوع المركبة / البند (يمكن اختيار أكثر من نوع)",
        [*vehicle_types, "مصروفات عامة"],
        key="rep_type_filter",
        help="اختر نوعاً واحداً أو أكثر. اترك القائمة فارغة لعرض كل الأنواع.",
        placeholder="كل الأنواع",
    )
    
    generate_btn = st.button(
        "📄 تجهيز التقرير الشامل للطباعة",
        type="primary",
        width="stretch",
    )

# استعلام جلب البيانات المباشر من جدول Logs الصحيح تماماً مثل صفحة السجلات
logs_query = """
    SELECT l.*, COALESCE(b.VehicleType, 'مصروفات عامة') AS VehicleType,
           COALESCE(b.VehicleUser, '') AS VehicleUser,
           b.Model
      FROM Logs l
      LEFT JOIN Buses b ON b.BusID = l.BusID
     ORDER BY COALESCE(l.DoneDate, '') DESC, l.LogID DESC
"""
logs_df = db.read_df(logs_query)

if not logs_df.empty:
    logs_df["_date"] = pd.to_datetime(logs_df["DoneDate"], errors="coerce")
    logs_df["_cost"] = pd.to_numeric(logs_df["Cost"], errors="coerce").fillna(0.0)
    # الأعمدة الجديدة اختيارية للسجلات القديمة: نرجع للعمود Cost عند غيابها.
    logs_df["_cost_incl"] = pd.to_numeric(
        logs_df.get("CostInclVAT", logs_df["_cost"]), errors="coerce"
    ).fillna(0.0)
    logs_df["_cost_incl"] = logs_df["_cost_incl"].where(
        logs_df["_cost_incl"] != 0, logs_df["_cost"]
    )
    logs_df["_cost_excl"] = pd.to_numeric(
        logs_df.get("CostExclVAT", logs_df["_cost_incl"]), errors="coerce"
    ).fillna(0.0)
    logs_df["_cost_excl"] = logs_df["_cost_excl"].where(
        logs_df["_cost_excl"] != 0, logs_df["_cost_incl"]
    )

if generate_btn:
    filtered_df = logs_df.copy() if not logs_df.empty else logs_df
    selected_types = [str(value) for value in type_filter if str(value).strip()]

    # تطبيق فلتر النوع والتاريخ (أكثر من نوع في نفس التقرير)
    if not filtered_df.empty and selected_types:
        type_mask = filtered_df["VehicleType"].astype(str).isin(selected_types)
        if "مصروفات عامة" in selected_types:
            type_mask |= filtered_df["BusID"].astype(str) == "مصروفات عامة"
        filtered_df = filtered_df[type_mask]

    # فلترة حسب الفترة المحددة (بتنطبق حتى لو مفيش نوع مختار)
    if not filtered_df.empty:
        filtered_df = filtered_df[
            (filtered_df["_date"].dt.date >= start_date)
            & (filtered_df["_date"].dt.date <= end_date)
        ]

    total_fleet_cost = 0.0
    total_fleet_cost_excl = 0.0
    groups: list[dict] = []

    if not filtered_df.empty:
        # تجميع السجلات حسب المركبة أو البند (BusID)
        grouped = filtered_df.groupby(
            ["BusID", "VehicleType", "VehicleUser"], sort=False
        )
        for (bus_id, v_type, v_user), group in grouped:
            bus_id_str = str(bus_id or "—")
            v_type_str = str(v_type or "مصروفات عامة")
            bus_cost = float(group["_cost_incl"].sum())
            bus_cost_excl = float(group["_cost_excl"].sum())
            total_fleet_cost += bus_cost
            total_fleet_cost_excl += bus_cost_excl

            rows: list[dict] = []
            for _, row in group.iterrows():
                rows.append(
                    {
                        "bus_id": bus_id_str,
                        "date": str(row.get("DoneDate") or "—"),
                        "job": str(row.get("JobType") or "—"),
                        "cost": float(row.get("_cost_incl") or 0.0),
                        "cost_excl": float(row.get("_cost_excl") or 0.0),
                        "cost_incl": float(row.get("_cost_incl") or 0.0),
                        "shop": str(row.get("Workshop") or "—"),
                        "status": str(row.get("InvoiceStatus") or "مدفوع"),
                    }
                )

            groups.append(
                {
                    "bus_id": bus_id_str,
                    "vehicle_type": v_type_str,
                    "vehicle_user": str(v_user or "—"),
                    "rows": rows,
                    "total": bus_cost,
                    "total_excl": bus_cost_excl,
                    "total_incl": bus_cost,
                }
            )

    report_bytes = pdf.build_comprehensive_report_pdf(
        start_date=start_date,
        end_date=end_date,
        type_filter=selected_types,
        groups=groups,
        total_cost=total_fleet_cost,
        total_cost_excl=total_fleet_cost_excl,
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
