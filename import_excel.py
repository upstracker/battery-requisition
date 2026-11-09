"""
สคริปต์นำเข้าข้อมูลรุ่นและยี่ห้อแบตเตอรี่จากไฟล์ Excel เข้าสู่ฐานข้อมูล SQLite (inventory.db)
"""
import os
import re
import sqlite3
import openpyxl

import app_paths
from services.catalog_rules import build_base_code, detect_brand


def import_batteries(excel_path=None, db_path=None, default_qty=10):
    excel_path = excel_path or app_paths.battery_excel_file()
    db_path = db_path or app_paths.db_file()
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"ไม่พบไฟล์ Excel: {excel_path}")

    wb = openpyxl.load_workbook(excel_path)
    sheet = wb.active
    rows = [str(sheet.cell(row=i, column=1).value).strip() 
            for i in range(2, sheet.max_row + 1) 
            if sheet.cell(row=i, column=1).value]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # กันรหัสซ้ำเฉพาะภายในไฟล์ Excel รอบนี้ ส่วนรหัสที่มีใน DB แล้วจะถูกอัปเดตด้วย ON CONFLICT
    # (นำเข้าซ้ำจะไม่สร้างรายการซ้ำแบบ "(#1)")
    seen_codes = set()

    imported_count = 0

    for idx, raw in enumerate(rows):
        # ข้ามยี่ห้อ 3K ตามที่ผู้ใช้กำหนด
        if re.search(r'(?i)\b3K\b', raw):
            continue

        # 1. ตรวจหายี่ห้อ (ต้องเป็นคำเดี่ยว: EFB ไม่ใช่ FB)
        brand = detect_brand(raw)

        # 2. ตรวจหาความจุ Ah
        ah_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:Ah|AH|A\b)', raw)
        capacity = f"{ah_match.group(1)} Ah" if ah_match else "-"

        # 3. ตรวจหาประเภทแบตเตอรี่
        raw_u = raw.upper()
        if 'AGM' in raw_u:
            b_type = 'AGM'
        elif 'EFB' in raw_u:
            b_type = 'EFB'
        elif 'SMF' in raw_u or 'แบตแห้ง' in raw or 'แบบแห้ง' in raw or 'แบตเเห้ง' in raw:
            b_type = 'แห้ง (SMF)'
        elif 'AMF' in raw_u:
            b_type = 'AMF (บำรุงรักษาน้อย)'
        elif 'DMF' in raw_u:
            b_type = 'DMF (ไม่ต้องเติมน้ำกลั่น)'
        elif 'น้ำ' in raw:
            b_type = 'น้ำ (Conventional)'
        elif 'HYBRID' in raw_u or 'ไฮบริด' in raw:
            b_type = 'ไฮบริด'
        else:
            b_type = 'กึ่งแห้ง (MF)'

        # 4. สร้างรหัสรุ่น (item_code)
        base_code = build_base_code(raw, brand)
        final_code = base_code
        counter = 1
        while final_code in seen_codes:
            final_code = f"{base_code} (#{counter})"
            counter += 1
        seen_codes.add(final_code)

        # 5. Insert หรือ Update ลงตาราง items
        cursor.execute("""
            INSERT INTO items (brand, item_code, item_name, capacity, battery_type, unit, stock_qty, min_qty)
            VALUES (?, ?, ?, ?, ?, 'ลูก', ?, 3)
            ON CONFLICT(item_code) DO UPDATE SET
                brand=excluded.brand,
                item_name=excluded.item_name,
                capacity=excluded.capacity,
                battery_type=excluded.battery_type
        """, (brand, final_code, raw, capacity, b_type, default_qty))
        imported_count += 1

    conn.commit()

    # นับจำนวนสรุป
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT brand) FROM items")
    total_items, total_brands = cursor.fetchone()
    conn.close()

    print("=" * 60)
    print(f"✅ นำเข้าข้อมูลแบตเตอรี่สำเร็จ: {imported_count} รายการ")
    print(f"📊 รวมสินค้าในฐานข้อมูล SQLite ปัจจุบัน: {total_items} รุ่น ({total_brands} ยี่ห้อ)")
    print("=" * 60)
    return imported_count, total_items

if __name__ == "__main__":
    from database.db import ensure_data_directory, get_db_file
    from database.migrations import run_migrations

    ensure_data_directory()
    run_migrations(get_db_file())
    import_batteries()
