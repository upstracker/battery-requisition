import os
import shutil
import sqlite3
from datetime import datetime

# เวอร์ชันโครงสร้างฐานข้อมูลล่าสุด
LATEST_SCHEMA_VERSION = 1


def snapshot_backup(db_path, reason="pre_migration"):
    """สร้างไฟล์ Snapshot สำรองฐานข้อมูลแบบเร่งด่วนก่อนการปรับโครงสร้าง"""
    if not os.path.exists(db_path):
        return None
    backup_dir = "database_backups"
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"snapshot_{reason}_{timestamp}.db")
    shutil.copy2(db_path, backup_file)
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


# ทะเบียนบันทึกฟังก์ชัน Migration ตามเวอร์ชัน
MIGRATIONS = {
    1: migration_v1,
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
