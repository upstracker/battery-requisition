import os
import sqlite3
from datetime import datetime

import app_paths
from services.catalog_rules import UNKNOWN_BRAND, build_base_code, detect_brand, _brand_pattern
from services.categories import BATTERY, OTHER_CATEGORIES
from services.dates import normalize_req_date

# เวอร์ชันโครงสร้างฐานข้อมูลล่าสุด
LATEST_SCHEMA_VERSION = 3


def snapshot_backup(db_path, reason="pre_migration"):
    """สร้างไฟล์ Snapshot สำรองฐานข้อมูลก่อนการปรับโครงสร้าง"""
    if not os.path.exists(db_path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(app_paths.backup_dir(), f"snapshot_{reason}_{timestamp}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_file)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return os.path.abspath(backup_file)


def migration_v1(cursor):
    """
    Migration Version 1:
    - ตาราง items (คลังแบตเตอรี่)
    - ตาราง requisitions (ใบเบิกสินค้า)
    - ตาราง requisition_items (รายการแบตเตอรี่ในใบเบิก)
    - ตาราง settings (การตั้งค่าหัวเอกสาร)
    - Indexes เพิ่มประสิทธิภาพ (Foreign Key & Fast Search)
    """
    # 1. ตาราง items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            item_code TEXT UNIQUE NOT NULL,
            item_name TEXT NOT NULL,
            capacity TEXT,
            battery_type TEXT,
            unit TEXT NOT NULL DEFAULT 'ลูก',
            stock_qty INTEGER NOT NULL DEFAULT 0,
            min_qty INTEGER NOT NULL DEFAULT 5,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. ตาราง requisitions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requisitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            req_no TEXT UNIQUE NOT NULL,
            req_date TEXT NOT NULL,
            driver_name TEXT NOT NULL,
            vehicle_plate TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            route_zone TEXT,
            ref_bill_no TEXT,
            purpose TEXT,
            status TEXT NOT NULL DEFAULT 'COMPLETED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. ตาราง requisition_items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requisition_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requisition_id INTEGER NOT NULL,
            item_id INTEGER,
            brand TEXT,
            item_code TEXT NOT NULL,
            item_name TEXT NOT NULL,
            capacity TEXT,
            unit TEXT NOT NULL DEFAULT 'ลูก',
            quantity INTEGER NOT NULL,
            remark TEXT,
            FOREIGN KEY (requisition_id) REFERENCES requisitions (id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE SET NULL
        );
    """)

    # 4. ตาราง settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # 5. สร้าง Indexes ทั้งหมด
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_req_items_req_id ON requisition_items (requisition_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_brand ON items (brand);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_code ON items (item_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_req_created ON requisitions (created_at DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_req_status ON requisitions (status);")


def _has_column(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _fix_misdetected_brands(cursor):
    """
    แก้ยี่ห้อที่ตัวนำเข้า Excel รุ่นเก่าเดาผิด (เช่น "GS ... EFB" ถูกนับเป็น FB เพราะมีคำว่า FB ใน EFB)
    เปลี่ยนเฉพาะเมื่อยี่ห้อเดิมไม่ได้ปรากฏเป็นคำเดี่ยวในชื่อสินค้าเลย
    """
    cursor.execute("SELECT id, brand, item_code, item_name FROM items")
    rows = cursor.fetchall()
    codes = {row[2] for row in rows}
    for item_id, brand, code, name in rows:
        new_brand = detect_brand(name)
        if new_brand in (UNKNOWN_BRAND, brand) or not brand:
            continue
        if _brand_pattern(brand.upper()).search(str(name).upper()):
            continue
        new_code = code
        if code == build_base_code(name, brand):
            candidate = build_base_code(name, new_brand)
            if candidate not in codes:
                new_code = candidate
        codes.discard(code)
        codes.add(new_code)
        cursor.execute(
            "UPDATE items SET brand = ?, item_code = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_brand, new_code, item_id),
        )


def _normalize_stored_dates(cursor):
    cursor.execute("SELECT id, req_date FROM requisitions")
    for req_id, req_date in cursor.fetchall():
        try:
            normalized = normalize_req_date(req_date)
        except ValueError:
            continue
        if normalized != req_date:
            cursor.execute("UPDATE requisitions SET req_date = ? WHERE id = ?", (normalized, req_id))


def migration_v2(cursor):
    """
    Migration Version 2:
    - เพิ่มช่อง category (หมวดสินค้า) ให้ items และ requisition_items แยกจากยี่ห้อ
    - จัดหมวดรายการเก่าที่เป็นอะไหล่/สินค้าอื่น (เดิมเก็บหมวดไว้ในช่องยี่ห้อ)
    - แก้ยี่ห้อแบตที่นำเข้าผิด และปรับรูปแบบวันที่ใบเบิกให้เป็น DD/MM/YYYY (ค.ศ.)
    """
    for table in ("items", "requisition_items"):
        if not _has_column(cursor, table, "category"):
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN category TEXT NOT NULL DEFAULT '{BATTERY}'")

    placeholders = ",".join("?" for _ in OTHER_CATEGORIES)
    cursor.execute(f"""
        UPDATE requisition_items SET category = brand
        WHERE item_id IS NULL AND brand IN ({placeholders}) AND item_name NOT LIKE ?
    """, (*OTHER_CATEGORIES, f"{BATTERY}%"))

    _fix_misdetected_brands(cursor)
    _normalize_stored_dates(cursor)


def migration_v3(cursor):
    """
    Migration Version 3:
    - เพิ่มเลขเวอร์ชันให้ใบเบิก เพื่อตรวจจับกรณีหลายเครื่องแก้ใบเดียวกันพร้อมกัน
    """
    if not _has_column(cursor, "requisitions", "version"):
        cursor.execute("ALTER TABLE requisitions ADD COLUMN version INTEGER NOT NULL DEFAULT 1")


# ทะเบียนบันทึกฟังก์ชัน Migration ตามเวอร์ชัน
MIGRATIONS = {
    1: migration_v1,
    2: migration_v2,
    3: migration_v3,
}


def run_migrations(db_path):
    """
    ตรวจสอบและรัน Schema Migration อัตโนมัติ:
    - ตรวจสอบ PRAGMA user_version
    - หากต่ำกว่า LATEST_SCHEMA_VERSION จะสำรองฐานข้อมูล และรัน Migration ทีละขั้น
    - ปลอดภัย 100% ไม่แตะต้องข้อมูลเดิม
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")

    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    current_version = cursor.fetchone()[0]

    if current_version < LATEST_SCHEMA_VERSION:
        # สำรองข้อมูลอัตโนมัติก่อนอัปเกรด
        if current_version > 0:
            snapshot_path = snapshot_backup(db_path, f"pre_v{current_version}_to_v{LATEST_SCHEMA_VERSION}")
            print(f"[*] Pre-migration snapshot created: {snapshot_path}")

        try:
            for ver in range(current_version + 1, LATEST_SCHEMA_VERSION + 1):
                if ver in MIGRATIONS:
                    print(f"[*] Applying schema migration version {ver}...")
                    MIGRATIONS[ver](cursor)
                    cursor.execute(f"PRAGMA user_version = {ver};")
                    conn.commit()
                    print(f"[+] Migration version {ver} applied successfully.")
        except Exception as e:
            conn.rollback()
            conn.close()
            raise RuntimeError(f"Failed to migrate database schema to version {ver}: {e}")

    conn.close()
    return True
