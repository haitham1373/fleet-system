"""بيان الركاب: تجهيز وطباعة كشف ركاب الرحلة دون حفظه في قاعدة البيانات."""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from core import auth, db, pdf, services, ui
from core.utils import clean_text

auth.require_login()
ui.page_header(
    "بيان الركاب",
    "تجهيز كشف ركاب الرحلة للطباعة أو الحفظ بصيغة PDF",
    "👥",
)

bus_labels = services.bus_labels()
default_route = "المدينة المنورة - مكة المكرمة"

st.markdown("#### بيانات الرحلة")
selection_first, selection_second, selection_third = st.columns(3)
with selection_first:
    selected_bus_label = st.selectbox(
        "المركبة (اختياري)",
        ["-- اختيار المركبة (اختياري) --", *bus_labels.values()],
        key="manifest_bus",
    )
with selection_second:
    passengers_count = st.number_input(
        "عدد الركاب",
        min_value=1,
        max_value=60,
        value=5,
        step=1,
        key="manifest_passengers_count",
    )
with selection_third:
    trip_date = st.date_input(
        "تاريخ الذهاب",
        value=date.today(),
        key="manifest_trip_date",
    )

selected_bus_id = (
    services.bus_id_from_label(selected_bus_label)
    if selected_bus_label != "-- اختيار المركبة (اختياري) --"
    else ""
)
bus_row = (
    db.fetch_one(
        "SELECT BusID FROM Buses WHERE BusID=?",
        (selected_bus_id,),
    )
    if selected_bus_id
    else None
)

with st.form("passenger_manifest_form"):
    st.markdown("##### بيانات السائق والحملة")
    first, second, third = st.columns(3)
    with first:
        campaign_name = st.text_input(
            "اسم الحملة",
            value="رحلات بروج العالم",
        )
        driver_name = st.text_input("اسم السائق")
        mobile_number = st.text_input("رقم الجوال")
    with second:
        route_plan = st.text_input("خط السير", value=default_route)
        bus_plate = st.text_input(
            "رقم اللوحة",
            value=str(bus_row.get("BusID") or "") if bus_row else "",
        )
        supervisor = st.text_input("المشرف")
    with third:
        operation_number = st.text_input("تشغيلة رقم")
        st.info("💡 يتم تجهيز الكشف مباشرة دون الحاجة لإجبارية إدخال البيانات.")

    st.markdown("---")
    st.markdown("##### بيانات الركاب")
    passengers: list[dict[str, str]] = []
    for index in range(int(passengers_count)):
        row_first, row_second, row_third = st.columns([2, 2, 1])
        with row_first:
            passenger_name = st.text_input(
                f"اسم الراكب {index + 1}",
                key=f"manifest_name_{index}",
            )
        with row_second:
            passenger_id = st.text_input(
                f"رقم الهوية / الإقامة {index + 1}",
                key=f"manifest_id_{index}",
            )
        with row_third:
            nationality = st.text_input(
                f"الجنسية {index + 1}",
                value="باكستاني",
                key=f"manifest_nationality_{index}",
            )
        passengers.append(
            {
                "name": clean_text(passenger_name, 120),
                "id": clean_text(passenger_id, 40),
                "nationality": clean_text(nationality, 60),
            }
        )

    submitted = st.form_submit_button(
        "⚙️ تجهيز بيان الركاب للطباعة",
        type="primary",
        width="stretch",
    )

if submitted:
    manifest_bytes = pdf.build_manifest_pdf(
        campaign_name=clean_text(campaign_name, 120),
        driver_name=clean_text(driver_name, 120),
        mobile_number=clean_text(mobile_number, 40),
        route_plan=clean_text(route_plan, 160),
        bus_plate=clean_text(bus_plate, 60),
        supervisor=clean_text(supervisor, 120),
        trip_date=trip_date,
        operation_number=clean_text(operation_number, 40),
        passengers=passengers,
    )
    st.session_state["manifest_file_name"] = (
        f"passenger_manifest_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    )
    st.session_state["manifest_file_bytes"] = manifest_bytes
    st.session_state["manifest_data_ready"] = True
    st.success("تم تجهيز بيان الركاب بصيغة PDF بنجاح.")

if st.session_state.get("manifest_data_ready"):
    st.divider()
    st.download_button(
        "🖨️ تحميل وطباعة بيان الركاب (PDF)",
        data=st.session_state["manifest_file_bytes"],
        file_name=st.session_state["manifest_file_name"],
        mime="application/pdf",
        type="primary",
        width="stretch",
        key="download_manifest",
    )
    st.caption("ملف PDF جاهز للطباعة أو الحفظ على الجهاز.")
