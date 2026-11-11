"""خدمات مشتركة تربط الكيانات وتزامن الحقول المشتقة.

هذه الوحدة تجمع العمليات التي تتكرر بين الصفحات مثل مزامنة بيانات
البطارية والفحص مع جدول المركبات، وتوليد معرفات العقود، وعرض قوائم
المركبات الموحدة.
"""

from __future__ import annotations

from datetime import datetime

from . import db
from .utils import add_months, days_until, parse_date, warranty_status


def bus_choices() -> list[str]:
    """أرقام جميع المركبات مرتبة."""
    return [
        str(value)
        for value in db.fetch_column("SELECT BusID FROM Buses ORDER BY BusID")
        if value
    ]


def bus_labels() -> dict[str, str]:
    """قاموس رقم المركبة إلى وصف يضم النوع والموديل."""
    rows = db.fetch_all(
        "SELECT BusID, VehicleType, Model FROM Buses ORDER BY BusID"
    )
    labels: dict[str, str] = {}
    for row in rows:
        bus_id = str(row.get("BusID") or "")
        if not bus_id:
            continue
        details = " - ".join(
            str(part)
            for part in (row.get("VehicleType"), row.get("Model"))
            if part
        )
        labels[bus_id] = f"{bus_id} ({details})" if details else bus_id
    return labels


def bus_id_from_label(label: str | None) -> str:
    """يستخرج رقم المركبة من الوصف المعروض في القوائم."""
    if not label:
        return ""
    return str(label).split(" (", 1)[0].strip()


def battery_expiry(install_date: object, warranty_months: object) -> str:
    """يحسب تاريخ انتهاء ضمان البطارية ويعيده نصاً."""
    try:
        months = int(warranty_months or 12)
    except (TypeError, ValueError):
        months = 12
    expiry = add_months(install_date, max(1, months))
    return expiry.strftime("%Y-%m-%d") if expiry else ""


def sync_bus_battery(bus_id: str) -> None:
    """يزامن أحدث بطارية مسجلة مع حقول البطارية القديمة في جدول المركبات."""
    if not bus_id:
        return

    latest = db.fetch_one(
        """
        SELECT *
          FROM Batteries
         WHERE BusID = ?
         ORDER BY COALESCE(InstallDate, '') DESC, ID DESC
         LIMIT 1
        """,
        (bus_id,),
    )

    if latest is None:
        db.execute(
            """
            UPDATE Buses
               SET BatteryStatus=NULL, BatteryInstallDate=NULL,
                   WarrantyExpiry=NULL, BatteryWarrantyFile=NULL,
                   UpdatedAt=?
             WHERE BusID=?
            """,
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bus_id),
        )
        return

    expiry = battery_expiry(latest.get("InstallDate"), latest.get("WarrantyMonths"))
    db.execute(
        """
        UPDATE Buses
           SET BatteryStatus=?, BatteryInstallDate=?, WarrantyExpiry=?,
               BatteryWarrantyFile=?, UpdatedAt=?
         WHERE BusID=?
        """,
        (
            latest.get("BatteryType") or latest.get("BatteryStatus") or "",
            latest.get("InstallDate") or "",
            expiry,
            latest.get("WarrantyFile") or latest.get("BatteryFile") or "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            bus_id,
        ),
    )


def battery_status_label(install_date: object, warranty_months: object) -> str:
    """يرجع حالة الضمان النصية لبطارية حسب تاريخ التركيب والمدة."""
    expiry = battery_expiry(install_date, warranty_months)
    return warranty_status(days_until(expiry))


def sync_bus_inspection(bus_id: str) -> None:
    """يزامن أحدث فحص دوري مع حقول الفحص في جدول المركبات."""
    if not bus_id:
        return

    latest = db.fetch_one(
        """
        SELECT InspectionDate, ExpiryDate
          FROM InspectionReports
         WHERE BusID = ?
         ORDER BY COALESCE(ExpiryDate, '') DESC, ReportID DESC
         LIMIT 1
        """,
        (bus_id,),
    )

    if latest is None:
        db.execute(
            """
            UPDATE Buses
               SET InspectionDate=NULL, DaysToInspection=NULL, UpdatedAt=?
             WHERE BusID=?
            """,
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bus_id),
        )
        return

    db.execute(
        """
        UPDATE Buses
           SET InspectionDate=?, DaysToInspection=?, UpdatedAt=?
         WHERE BusID=?
        """,
        (
            latest.get("InspectionDate") or "",
            days_until(latest.get("ExpiryDate")),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            bus_id,
        ),
    )


def next_parking_contract_id() -> str:
    """يولد معرفاً نصياً متسلسلاً لعقد مواقف جديد."""
    values = db.fetch_column("SELECT ContractID FROM ParkingContracts")
    highest = 0
    for value in values:
        digits = "".join(character for character in str(value or "") if character.isdigit())
        if digits:
            highest = max(highest, int(digits))
    return f"PC-{highest + 1:05d}"


def contract_status(end_date: object) -> str:
    """حالة العقد حسب تاريخ الانتهاء."""
    days = days_until(end_date)
    if days is None:
        return "غير محدد"
    if days < 0:
        return "منتهي"
    if days <= 30:
        return "قريب الانتهاء"
    return "ساري"


def latest_batteries_df():
    """يرجع أحدث بطارية لكل مركبة مع تاريخ الانتهاء والحالة."""
    frame = db.read_df(
        """
        SELECT bt.*, b.VehicleType, b.Model
          FROM Batteries bt
          LEFT JOIN Buses b ON b.BusID = bt.BusID
         ORDER BY COALESCE(bt.InstallDate, '') DESC, bt.ID DESC
        """
    )
    if frame.empty:
        return frame
    frame["تاريخ الانتهاء"] = frame.apply(
        lambda row: battery_expiry(row.get("InstallDate"), row.get("WarrantyMonths")),
        axis=1,
    )
    frame["أيام متبقية"] = frame["تاريخ الانتهاء"].apply(days_until)
    frame["حالة الضمان"] = frame["أيام متبقية"].apply(warranty_status)
    return frame


def parse_contract_date(value: object) -> str:
    """يعيد التاريخ بصيغة موحدة أو نصاً فارغاً."""
    parsed = parse_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed else ""
