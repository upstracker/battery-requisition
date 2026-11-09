import os
import re
import sqlite3
from datetime import datetime

import app_paths
from database.migrations import run_migrations

REQ_NO_PATTERN = re.compile(r"^(REQ-\d{6}-)(\d+)$")


def get_db_file():
    return app_paths.db_file()


def _copy_sqlite(src, dst):
    """คัดลอกฐานข้อมูลด้วย backup API ของ SQLite (รวมข้อมูลที่ค้างในไฟล์ -wal ด้วย)"""
    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def ensure_data_directory():
    """
    สร้างโฟลเดอร์ข้อมูล และย้ายฐานข้อมูลเดิมมาไว้ที่ตำแหน่งใหม่ในครั้งแรก
    (inventory.db ที่รูทโปรเจกต์ หรือ {โฟลเดอร์โปรแกรม}\\data ของตัวติดตั้งรุ่นก่อน)
    """
    db_path = get_db_file()
    if os.path.exists(db_path):
        return
    for legacy in app_paths.legacy_db_candidates():
        if os.path.abspath(legacy) != os.path.abspath(db_path) and os.path.exists(legacy):
            try:
                _copy_sqlite(legacy, db_path)
                print(f"[*] Migrated legacy database {legacy} -> {db_path}")
                return
            except Exception as e:
                print(f"[!] Warning: Failed to copy legacy database {legacy}: {e}")


def daily_auto_backup():
    """สำรองฐานข้อมูลอัตโนมัติวันละ 1 ครั้งเมื่อเปิดโปรแกรม (database_backups/auto_daily_YYYYMMDD.db)"""
    db_path = get_db_file()
    if not os.path.exists(db_path):
        return None

    today_str = datetime.now().strftime("%Y%m%d")
    daily_backup_path = os.path.join(app_paths.backup_dir(), f"auto_daily_{today_str}.db")

    if not os.path.exists(daily_backup_path):
        try:
            _copy_sqlite(db_path, daily_backup_path)
            print(f"[*] Daily safety snapshot created: {daily_backup_path}")
        except Exception as e:
            print(f"[!] Warning: Daily backup failed: {e}")
    return daily_backup_path


def get_connection():
    conn = sqlite3.connect(get_db_file(), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db():
    ensure_data_directory()
    daily_auto_backup()

    run_migrations(get_db_file())

    conn = get_connection()
    cursor = conn.cursor()

    default_settings = [
        ("company_name", "บริษัท คลังแบตเตอรี่และบริการ จำกัด"),
        ("slip_title", "ใบเบิกและจ่ายสินค้าขึ้นรถส่งของ (BATTERY LOADING & DELIVERY SLIP)"),
        ("sign_role_1", "พนักงานขับรถ / ผู้รับของขึ้นรถ"),
        ("sign_role_2", "เจ้าหน้าที่จัดจ่ายคลังสินค้า"),
        ("sign_role_3", "ผู้อนุมัติ / หัวหน้าคลัง"),
    ]
    for k, v in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    cursor.execute("SELECT COUNT(*) AS count FROM items")
    is_empty = cursor.fetchone()["count"] == 0
    conn.commit()
    conn.close()

    # เครื่องใหม่: นำเข้ารุ่นแบตเตอรี่จาก Excel ลงฐานข้อมูลที่โปรแกรมใช้งานจริง
    excel_path = app_paths.battery_excel_file()
    if is_empty and os.path.exists(excel_path):
        try:
            from import_excel import import_batteries
            import_batteries(excel_path=excel_path, db_path=get_db_file())
        except Exception as e:
            print(f"[!] Excel import note: {e}")


def _seq_setting_key(prefix):
    return f"last_req_seq:{prefix}"


def record_issued_req_no(cursor, req_no):
    """จำเลขล่าสุดที่เคยออกไว้ เพื่อไม่ให้เลขของใบที่ถูกลบถาวรถูกนำกลับมาใช้ซ้ำ"""
    m = REQ_NO_PATTERN.match(req_no or "")
    if not m:
        return
    prefix, num = m.group(1), int(m.group(2))
    key = _seq_setting_key(prefix)
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    current = int(row[0]) if row and str(row[0]).isdigit() else 0
    if num > current:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(num)))


def generate_next_req_no():
    """สร้างเลขที่ใบเบิกอัตโนมัติ เช่น REQ-202609-0001"""
    prefix = f"REQ-{datetime.now().strftime('%Y%m')}-"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT req_no FROM requisitions WHERE req_no LIKE ?", (f"{prefix}%",))
    last_num = 0
    for row in cursor.fetchall():
        m = REQ_NO_PATTERN.match(row["req_no"])
        if m and m.group(1) == prefix:
            last_num = max(last_num, int(m.group(2)))
    cursor.execute("SELECT value FROM settings WHERE key = ?", (_seq_setting_key(prefix),))
    row = cursor.fetchone()
    if row and str(row["value"]).isdigit():
        last_num = max(last_num, int(row["value"]))
    conn.close()

    return f"{prefix}{last_num + 1:04d}"


if __name__ == "__main__":
    init_db()
    print("Battery Database initialized successfully.")
    print("Database path:", get_db_file())
    print("Next sample req no:", generate_next_req_no())
