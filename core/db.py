"""طبقة الوصول إلى قاعدة البيانات وإنشاء الجداول والترحيلات."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from .config import BACKUP_DIR, DB_PATH, ensure_directories
from .security import hash_password
from .utils import (
    clean_text,
    days_until,
    maintenance_status,
    parse_date,
    warranty_status,
)

# ---------------------------------------------------------------------------
# الاتصال
# ---------------------------------------------------------------------------
@contextmanager
def get_conn():
    """اتصال آمن بقاعدة البيانات مع معاملة تلقائية وإغلاق مضمون."""
    ensure_directories()
    connection = sqlite3.connect(str(DB_PATH), timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_all(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    with get_conn() as connection:
        rows = connection.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def fetch_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    with get_conn() as connection:
        row = connection.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None


def fetch_column(sql: str, params: Sequence[Any] = ()) -> list[Any]:
    with get_conn() as connection:
        return [row[0] for row in connection.execute(sql, tuple(params)).fetchall()]


def scalar(sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
    row = fetch_one(sql, params)
    if not row:
        return default
    return next(iter(row.values()))


def read_df(sql: str, params: Sequence[Any] = ()) -> pd.DataFrame:
    with get_conn() as connection:
        return pd.read_sql_query(sql, connection, params=tuple(params))


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    with get_conn() as connection:
        cursor = connection.execute(sql, tuple(params))
        return int(cursor.lastrowid or 0)


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    with get_conn() as connection:
        connection.executemany(sql, [tuple(row) for row in rows])


def log_audit(
    username: str,
    action: str,
    entity: str,
    entity_key: object = "",
    details: str = "",
) -> None:
    """يسجل حركة في سجل التدقيق."""
    with get_conn() as connection:
        connection.execute(
            """
            INSERT INTO AuditLog (At, Username, Action, Entity, EntityKey, Details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                clean_text(username, 80),
                clean_text(action, 80),
                clean_text(entity, 120),
                clean_text(entity_key, 120),
                clean_text(details, 1000),
            ),
        )


# ---------------------------------------------------------------------------
# الجداول
# ---------------------------------------------------------------------------
_TABLES: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS Users (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Username TEXT UNIQUE NOT NULL,
        Password TEXT NOT NULL,
        FullName TEXT,
        Role TEXT NOT NULL DEFAULT 'user',
        IsActive INTEGER NOT NULL DEFAULT 1,
        CreatedAt TEXT,
        LastLoginAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS VehicleTypes (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        TypeName TEXT UNIQUE NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS Workshops (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        WorkshopName TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS MaintenanceTypes (
        JobTypeName TEXT PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS HotelsList (
        HotelName TEXT PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS StationsList (
        StationName TEXT PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS Buses (
        BusID TEXT PRIMARY KEY,
        VehicleType TEXT,
        Model TEXT,
        OperationNumber TEXT,
        OdoCurrent REAL,
        OdoLast REAL,
        KmRemaining REAL,
        LastDate TEXT,
        NextDate TEXT,
        MaintType TEXT,
        Notes TEXT,
        InspectionDate TEXT,
        DaysToInspection INTEGER,
        DaysToMaintenance INTEGER,
        AlertStatus TEXT,
        BatteryStatus TEXT,
        WarrantyExpiry TEXT,
        BatteryInstallDate TEXT,
        OilValidity INTEGER,
        BatteryWarrantyFile TEXT,
        CreatedAt TEXT,
        UpdatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS Logs (
        LogID INTEGER PRIMARY KEY AUTOINCREMENT,
        BusID TEXT,
        DoneDate TEXT,
        JobType TEXT,
        Cost REAL,
        Workshop TEXT,
        InvoiceStatus TEXT,
        InvoiceFile TEXT,
        Notes TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS Batteries (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        BusID TEXT,
        BatteryType TEXT,
        InstallDate TEXT,
        WarrantyMonths INTEGER,
        WarrantyDaysLeft INTEGER,
        BatteryStatus TEXT,
        BatteryFile TEXT,
        Workshop TEXT,
        WarrantyFile TEXT,
        DaysRemaining INTEGER,
        WarrantyStatus TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS InspectionReports (
        ReportID INTEGER PRIMARY KEY AUTOINCREMENT,
        BusID TEXT,
        InspectionDate TEXT,
        ExpiryDate TEXT,
        ResultStatus TEXT,
        ReportFile TEXT,
        Notes TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS HotelContracts (
        ContractID INTEGER PRIMARY KEY AUTOINCREMENT,
        HotelName TEXT,
        BusID TEXT,
        StartDate TEXT,
        EndDate TEXT,
        ContractCost REAL,
        ContractFile TEXT,
        Notes TEXT,
        StationName TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS SmartParkingInvoices (
        ParkingID INTEGER PRIMARY KEY AUTOINCREMENT,
        BusID TEXT,
        ParkingLocation TEXT,
        ParkingDate TEXT,
        Cost REAL,
        InvoiceFile TEXT,
        Notes TEXT,
        HotelName TEXT,
        StationName TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ParkingContracts (
        ContractID TEXT PRIMARY KEY,
        ParkingName TEXT,
        StartDate TEXT,
        EndDate TEXT,
        Amount REAL,
        ContractFile TEXT,
        Notes TEXT,
        HotelName TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ParkingBills (
        BillID INTEGER PRIMARY KEY AUTOINCREMENT,
        HotelName TEXT,
        ParkingName TEXT,
        BillMonth TEXT,
        BillYear TEXT,
        Amount REAL,
        BillFile TEXT,
        Notes TEXT,
        CreatedAt TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS AuditLog (
        AuditID INTEGER PRIMARY KEY AUTOINCREMENT,
        At TEXT,
        Username TEXT,
        Action TEXT,
        Entity TEXT,
        EntityKey TEXT,
        Details TEXT
    )
    """,
)

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_logs_bus ON Logs(BusID)",
    "CREATE INDEX IF NOT EXISTS idx_logs_date ON Logs(DoneDate)",
    "CREATE INDEX IF NOT EXISTS idx_insp_bus ON InspectionReports(BusID)",
    "CREATE INDEX IF NOT EXISTS idx_insp_expiry ON InspectionReports(ExpiryDate)",
    "CREATE INDEX IF NOT EXISTS idx_batteries_bus ON Batteries(BusID)",
    "CREATE INDEX IF NOT EXISTS idx_parking_date ON SmartParkingInvoices(ParkingDate)",
    "CREATE INDEX IF NOT EXISTS idx_hotel_contracts_end ON HotelContracts(EndDate)",
    "CREATE INDEX IF NOT EXISTS idx_audit_at ON AuditLog(At)",
)

_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "Users": {
        "Role": "TEXT NOT NULL DEFAULT 'user'",
        "IsActive": "INTEGER NOT NULL DEFAULT 1",
        "CreatedAt": "TEXT",
        "LastLoginAt": "TEXT",
    },
    "Buses": {
        "VehicleType": "TEXT DEFAULT 'باص'",
        "BatteryStatus": "TEXT",
        "WarrantyExpiry": "TEXT",
        "BatteryInstallDate": "TEXT",
        "OilValidity": "INTEGER",
        "BatteryWarrantyFile": "TEXT",
        "Notes": "TEXT",
        "CreatedAt": "TEXT",
        "UpdatedAt": "TEXT",
    },
    "Logs": {
        "Notes": "TEXT",
        "CreatedAt": "TEXT",
    },
    "Batteries": {
        "Workshop": "TEXT",
        "WarrantyFile": "TEXT",
        "DaysRemaining": "INTEGER",
        "WarrantyStatus": "TEXT",
        "CreatedAt": "TEXT",
    },
    "InspectionReports": {
        "CreatedAt": "TEXT",
    },
    "HotelContracts": {
        "StationName": "TEXT",
        "CreatedAt": "TEXT",
    },
    "SmartParkingInvoices": {
        "HotelName": "TEXT",
        "StationName": "TEXT",
        "CreatedAt": "TEXT",
    },
    "ParkingContracts": {
        "HotelName": "TEXT",
        "CreatedAt": "TEXT",
    },
    "ParkingBills": {
        "CreatedAt": "TEXT",
    },
}


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table, columns in _COLUMN_MIGRATIONS.items():
        existing = _table_columns(connection, table)
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )


def _migrate_data(connection: sqlite3.Connection) -> None:
    """إصلاحات بيانات آمنة وقابلة للتكرار."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # إزالة تكرار أسماء الورش قبل إنشاء فهرس فريد.
    connection.execute(
        """
        DELETE FROM Workshops
        WHERE rowid NOT IN (SELECT MIN(rowid) FROM Workshops GROUP BY WorkshopName)
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_workshops_name ON Workshops(WorkshopName)"
    )

    # ضمان وجود دور صالح لكل مستخدم ومدير واحد على الأقل.
    connection.execute("UPDATE Users SET Role='admin' WHERE LOWER(Username)='admin'")
    connection.execute("UPDATE Users SET Role='user' WHERE Role IS NULL OR TRIM(Role)=''")
    connection.execute("UPDATE Users SET IsActive=1 WHERE IsActive IS NULL")
    connection.execute(
        "UPDATE Users SET CreatedAt=? WHERE CreatedAt IS NULL OR TRIM(CreatedAt)=''",
        (now,),
    )
    admin_exists = connection.execute(
        "SELECT COUNT(*) FROM Users WHERE Role='admin' AND IsActive=1"
    ).fetchone()[0]
    if not admin_exists:
        first_user = connection.execute(
            "SELECT ID FROM Users ORDER BY ID LIMIT 1"
        ).fetchone()
        if first_user:
            connection.execute(
                "UPDATE Users SET Role='admin', IsActive=1 WHERE ID=?",
                (first_user[0],),
            )

    # ترحيل كلمات المرور القديمة غير المشفرة.
    for row in connection.execute("SELECT ID, Password FROM Users").fetchall():
        stored = row["Password"]
        if stored and not str(stored).startswith("pbkdf2$"):
            connection.execute(
                "UPDATE Users SET Password=? WHERE ID=?",
                (hash_password(str(stored)), row["ID"]),
            )

    # منح عقود المواقف القديمة معرفاً نصياً.
    for row in connection.execute(
        "SELECT rowid, ContractID FROM ParkingContracts "
        "WHERE ContractID IS NULL OR TRIM(ContractID)=''"
    ).fetchall():
        connection.execute(
            "UPDATE ParkingContracts SET ContractID=? WHERE rowid=?",
            (f"PC-{int(row['rowid']):05d}", row["rowid"]),
        )

    # ترحيل بيانات البطاريات القديمة من جدول المركبات إلى جدول البطاريات.
    legacy_buses = connection.execute(
        """
        SELECT BusID, BatteryStatus, BatteryInstallDate, WarrantyExpiry,
               BatteryWarrantyFile
        FROM Buses
        WHERE BatteryStatus IS NOT NULL AND TRIM(BatteryStatus) <> ''
        """
    ).fetchall()
    for bus in legacy_buses:
        install_date = parse_date(bus["BatteryInstallDate"])
        expiry_date = parse_date(bus["WarrantyExpiry"])
        existing = connection.execute(
            """
            SELECT 1 FROM Batteries
            WHERE BusID=? AND COALESCE(InstallDate, '')=?
            LIMIT 1
            """,
            (bus["BusID"], str(install_date) if install_date else ""),
        ).fetchone()
        if existing:
            continue

        warranty_months = 12
        if install_date and expiry_date:
            warranty_months = max(
                1,
                (expiry_date.year - install_date.year) * 12
                + (expiry_date.month - install_date.month),
            )
        days = days_until(expiry_date)
        connection.execute(
            """
            INSERT INTO Batteries (
                BusID, BatteryType, InstallDate, WarrantyMonths,
                WarrantyDaysLeft, BatteryStatus, BatteryFile, Workshop,
                WarrantyFile, DaysRemaining, WarrantyStatus, CreatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bus["BusID"],
                bus["BatteryStatus"],
                str(install_date) if install_date else "",
                warranty_months,
                days,
                bus["BatteryStatus"],
                "",
                "",
                bus["BatteryWarrantyFile"] or "",
                days,
                warranty_status(days),
                now,
            ),
        )

    # إعادة حساب تنبيهات الصيانة من تاريخ الصيانة القادمة.
    for bus in connection.execute(
        "SELECT BusID, NextDate FROM Buses"
    ).fetchall():
        days = days_until(bus["NextDate"])
        connection.execute(
            "UPDATE Buses SET DaysToMaintenance=?, AlertStatus=? WHERE BusID=?",
            (days, maintenance_status(days), bus["BusID"]),
        )


def _seed_data(connection: sqlite3.Connection) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if connection.execute("SELECT COUNT(*) FROM Users").fetchone()[0] == 0:
        initial_password = os.environ.get("FLEET_ADMIN_PASSWORD", "1234")
        connection.execute(
            """
            INSERT INTO Users (Username, Password, FullName, Role, IsActive, CreatedAt)
            VALUES (?, ?, ?, 'admin', 1, ?)
            """,
            ("admin", hash_password(initial_password), "مدير النظام", now),
        )

    if connection.execute("SELECT COUNT(*) FROM VehicleTypes").fetchone()[0] == 0:
        connection.executemany(
            "INSERT OR IGNORE INTO VehicleTypes (TypeName) VALUES (?)",
            [
                ("حافلة كبيرة",),
                ("حافلة صغيرة",),
                ("ميني باص",),
                ("سيارة خاصة",),
            ],
        )

    if connection.execute("SELECT COUNT(*) FROM Workshops").fetchone()[0] == 0:
        connection.executemany(
            "INSERT OR IGNORE INTO Workshops (WorkshopName) VALUES (?)",
            [
                ("مركز الصيانة الرئيسي",),
                ("ورشة النور المركزية",),
            ],
        )

    if connection.execute("SELECT COUNT(*) FROM MaintenanceTypes").fetchone()[0] == 0:
        connection.executemany(
            "INSERT OR IGNORE INTO MaintenanceTypes (JobTypeName) VALUES (?)",
            [
                ("صيانة دورية",),
                ("تغيير زيت",),
                ("تغيير إطارات",),
                ("صيانة ميكانيكية",),
                ("صيانة كهربائية",),
            ],
        )


def init_db() -> None:
    """ينشئ قاعدة البيانات ويرحّل البيانات القديمة بأمان."""
    ensure_directories()
    with get_conn() as connection:
        for statement in _TABLES:
            connection.execute(statement)
        _apply_column_migrations(connection)
        for statement in _INDEXES:
            connection.execute(statement)
        _migrate_data(connection)
        _seed_data(connection)


# ---------------------------------------------------------------------------
# أدوات مساعدة
# ---------------------------------------------------------------------------
def database_size_bytes() -> int:
    try:
        return DB_PATH.stat().st_size
    except OSError:
        return 0


def table_count(table: str) -> int:
    allowed = {
        "Users",
        "Buses",
        "Logs",
        "Batteries",
        "InspectionReports",
        "HotelContracts",
        "SmartParkingInvoices",
        "ParkingContracts",
        "ParkingBills",
        "AuditLog",
    }
    if table not in allowed:
        raise ValueError("اسم جدول غير مسموح.")
    return int(scalar(f"SELECT COUNT(*) FROM {table}", default=0) or 0)


def _unique_backup_path() -> Path:
    """يعيد مساراً فريداً لنسخة احتياطية جديدة."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    candidate = BACKUP_DIR / f"fleet_backup_{stamp}.db"
    counter = 2
    while candidate.exists():
        candidate = BACKUP_DIR / f"fleet_backup_{stamp}_{counter}.db"
        counter += 1
    return candidate


def _checkpoint_truncate(connection: sqlite3.Connection) -> None:
    """ينفّذ checkpoint كاملاً ويرفض المتابعة إذا كان الملف مشغولاً."""
    row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    # الصيغة: (busy, log_frames, checkpointed_frames)
    if row is not None and int(row[0]) != 0:
        raise RuntimeError(
            "قاعدة البيانات مشغولة بعملية أخرى. أغلق الجلسات الأخرى وأعد المحاولة."
        )


def create_server_backup() -> Path:
    """ينشئ نسخة احتياطية متسقة باستخدام واجهة SQLite الرسمية.

    ملاحظة مهمة: ``with sqlite3.connect(...)`` لا يغلق الاتصال بل يكتفي
    بعمل commit، وترك الاتصالات مفتوحة يبقي صفحات WAL القديمة حيّة ويمنع
    الاستعادة من استبدال البيانات. لذلك نغلق الاتصالات صراحةً دائماً.
    """
    ensure_directories()
    destination = _unique_backup_path()
    source = sqlite3.connect(str(DB_PATH), timeout=30.0)
    target = sqlite3.connect(str(destination))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    return destination


def restore_from_file(source_path: Path | str) -> Path:
    """يستعيد قاعدة البيانات بعد أخذ نسخة أمان تلقائية.

    يتم تنفيذ نقطة استرجاع (WAL checkpoint) قبل النسخ وبعده، مع إغلاق كل
    الاتصالات صراحةً، حتى لا تعيد صفحات WAL القديمة البيانات المستبدلة.
    """
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError("ملف النسخة الاحتياطية غير موجود.")

    safety_backup = create_server_backup()

    target = sqlite3.connect(str(DB_PATH), timeout=30.0)
    source = sqlite3.connect(str(source_path))
    try:
        _checkpoint_truncate(target)
        source.backup(target)
        _checkpoint_truncate(target)
        target.commit()
    finally:
        source.close()
        target.close()

    init_db()
    return safety_backup
