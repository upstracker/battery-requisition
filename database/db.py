import sqlite3
import os
import shutil
from datetime import datetime
from database.migrations import run_migrations, LATEST_SCHEMA_VERSION

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_FILE = os.path.join(DATA_DIR, "inventory.db")


def ensure_data_directory():
    """
    ตรวจสอบและสร้างโฟลเดอร์ data/ พร้อมย้าย inventory.db เดิมมายัง data/inventory.db
    เพื่อให้ข้อมูลปลอดภัยจากการถูกเขียนทับเวลาอัปเดตโค้ดหรือแตกไฟล์ทับ
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    # หากมี inventory.db เดิมอยู่ที่รูทโปรเจกต์ แต่ยังไม่มีใน data/ ให้ย้ายมาที่ data/ อย่างปลอดภัย
    legacy_root_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inventory.db")
    if os.path.exists(legacy_root_db) and not os.path.exists(DB_FILE):
        try:
            shutil.copy2(legacy_root_db, DB_FILE)
            print(f"[*] Migrated legacy root database to isolated data folder: {DB_FILE}")
        except Exception as e:
            print(f"[!] Warning: Failed to copy legacy database: {e}")


def daily_auto_backup():
    """
    สำรองฐานข้อมูลอัตโนมัติวันละ 1 ครั้งเมื่อเปิดโปรแกรม
    บันทึกเป็น database_backups/auto_daily_YYYYMMDD.db
    """
    if not os.path.exists(DB_FILE):
        return None

    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database_backups")
    os.makedirs(backup_dir, exist_ok=True)

    today_str = datetime.now().strftime("%Y%m%d")
    daily_backup_path = os.path.join(backup_dir, f"auto_daily_{today_str}.db")

    if not os.path.exists(daily_backup_path):
        try:
            shutil.copy2(DB_FILE, daily_backup_path)
            print(f"[*] Daily safety snapshot created: {daily_backup_path}")
            return daily_backup_path
        except Exception as e:
            print(f"[!] Warning: Daily backup failed: {e}")
    return daily_backup_path


def get_connection():
    ensure_data_directory()
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db():
    ensure_data_directory()
    daily_auto_backup()

    # 1. รันระบบ Migration ตรวจสอบและอัปเกรดโครงสร้างตารางอัตโนมัติ
    run_migrations(DB_FILE)

    conn = get_connection()
    cursor = conn.cursor()

    # ค่าเริ่มต้นสำหรับงานคลังแบตเตอรี่
    default_settings = [
        ("company_name", "บริษัท คลังแบตเตอรี่และบริการ จำกัด"),
        ("slip_title", "ใบเบิกและจ่ายสินค้าขึ้นรถส่งของ (BATTERY LOADING & DELIVERY SLIP)"),
        ("sign_role_1", "พนักงานขับรถ / ผู้รับของขึ้นรถ"),
        ("sign_role_2", "เจ้าหน้าที่จัดจ่ายคลังสินค้า"),
        ("sign_role_3", "ผู้อนุมัติ / หัวหน้าคลัง"),
    ]
    for k, v in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # ถ้ายังไม่มีข้อมูลสินค้า และมีไฟล์ รุ่นแบตเตอรี่.xlsx ให้นำเข้าข้อมูลจริงอัตโนมัติ
    cursor.execute("SELECT COUNT(*) as count FROM items")
    excel_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "รุ่นแบตเตอรี่.xlsx")
    if cursor.fetchone()["count"] == 0 and os.path.exists(excel_path):
        conn.commit()
        conn.close()
        try:
            from import_excel import import_batteries
            import_batteries()
        except Exception as e:
            print(f"[!] Excel import note: {e}")
        return

    conn.commit()
    conn.close()


def generate_next_req_no():
    """สร้างเลขที่ใบเบิกอัตโนมัติ เช่น REQ-202609-0001"""
    now = datetime.now()
    prefix = f"REQ-{now.strftime('%Y%m')}-"
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT req_no FROM requisitions 
        WHERE req_no LIKE ? 
        ORDER BY id DESC LIMIT 1
    """, (f"{prefix}%",))
    row = cursor.fetchone()
    conn.close()

    if row:
        last_num = int(row["req_no"].split("-")[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"{prefix}{next_num:04d}"


if __name__ == "__main__":
    init_db()
    print("Battery Database initialized successfully.")
    print("Database path:", DB_FILE)
    print("Next sample req no:", generate_next_req_no())
