import os
import shutil
from datetime import datetime
from database.db import get_connection, generate_next_req_no, DB_FILE

def get_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {row["key"]: row["value"] for row in cursor.fetchall()}
    conn.close()
    return settings

def update_settings(settings_dict):
    conn = get_connection()
    cursor = conn.cursor()
    for k, v in settings_dict.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()

def get_all_items(search_text=""):
    conn = get_connection()
    cursor = conn.cursor()
    if search_text:
        query = "%" + search_text.strip() + "%"
        cursor.execute("""
            SELECT * FROM items 
            WHERE brand LIKE ? OR item_code LIKE ? OR item_name LIKE ?
            ORDER BY brand ASC, item_code ASC
        """, (query, query, query))
    else:
        cursor.execute("SELECT * FROM items ORDER BY brand ASC, item_code ASC")
    items = cursor.fetchall()
    conn.close()
    return [dict(ix) for ix in items]

def add_item(brand, item_code, item_name, capacity="45 Ah", battery_type="กึ่งแห้ง (MF)", unit="ลูก", stock_qty=0, min_qty=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO items (brand, item_code, item_name, capacity, battery_type, unit, stock_qty, min_qty)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (brand.strip(), item_code.strip(), item_name.strip(), capacity.strip(), battery_type.strip(), unit.strip(), int(stock_qty), int(min_qty)))
    conn.commit()
    conn.close()

def update_item(item_id, brand, item_code, item_name, capacity, battery_type, unit, stock_qty, min_qty):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE items 
        SET brand = ?, item_code = ?, item_name = ?, capacity = ?, battery_type = ?, unit = ?, stock_qty = ?, min_qty = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (brand.strip(), item_code.strip(), item_name.strip(), capacity.strip(), battery_type.strip(), unit.strip(), int(stock_qty), int(min_qty), item_id))
    conn.commit()
    conn.close()

def restock_item(item_id, added_qty):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE items 
        SET stock_qty = stock_qty + ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (int(added_qty), item_id))
    conn.commit()
    conn.close()

def delete_item(item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def create_requisition(driver_name, vehicle_plate, customer_name, route_zone, ref_bill_no, purpose, req_items, custom_req_no=None, req_date=None):
    """
    สร้างใบเบิกแบตเตอรี่ขึ้นรถส่งของ พร้อมตัดสต็อกสินค้าในคลัง
    """
    if not req_items:
        raise ValueError("กรุณาเลือกรายการแบตเตอรี่อย่างน้อย 1 รายการ")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 1. ตรวจสอบจำนวนเบิก
        for it in req_items:
            qty = int(it.get("quantity", 0))
            if qty <= 0:
                raise ValueError(f"จำนวนเบิกสำหรับรุ่น {it.get('item_code')} ต้องมากกว่า 0")

        # 2. สร้างเลขที่ใบเบิก
        final_req_no = custom_req_no if custom_req_no else generate_next_req_no()
        final_date = req_date if req_date else datetime.now().strftime("%d/%m/%Y")

        # 3. บันทึกหัวใบเบิก
        cursor.execute("""
            INSERT INTO requisitions (req_no, req_date, driver_name, vehicle_plate, customer_name, route_zone, ref_bill_no, purpose, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED')
        """, (final_req_no, final_date, driver_name.strip(), vehicle_plate.strip(), customer_name.strip(), route_zone.strip(), ref_bill_no.strip(), purpose.strip()))
        req_id = cursor.lastrowid

        # 4. บันทึกรายการสินค้าในใบเบิก
        for it in req_items:
            item_id = it.get("item_id")
            qty = int(it["quantity"])
            cursor.execute("""
                INSERT INTO requisition_items (requisition_id, item_id, brand, item_code, item_name, capacity, unit, quantity, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (req_id, item_id, it.get("brand", ""), it["item_code"], it["item_name"], it.get("capacity", ""), it.get("unit", "ลูก"), qty, it.get("remark", "")))

        conn.commit()
        return req_id, final_req_no

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_requisitions_list(search_text=""):
    conn = get_connection()
    cursor = conn.cursor()
    if search_text:
        q = "%" + search_text.strip() + "%"
        cursor.execute("""
            SELECT r.*, 
                   COUNT(ri.id) as item_count,
                   SUM(ri.quantity) as total_units
            FROM requisitions r
            LEFT JOIN requisition_items ri ON r.id = ri.requisition_id
            WHERE r.req_no LIKE ? OR r.driver_name LIKE ? OR r.vehicle_plate LIKE ? OR r.customer_name LIKE ? OR r.ref_bill_no LIKE ?
            GROUP BY r.id
            ORDER BY r.id DESC
            LIMIT 200
        """, (q, q, q, q, q))
    else:
        cursor.execute("""
            SELECT r.*, 
                   COUNT(ri.id) as item_count,
                   SUM(ri.quantity) as total_units
            FROM requisitions r
            LEFT JOIN requisition_items ri ON r.id = ri.requisition_id
            GROUP BY r.id
            ORDER BY r.id DESC
            LIMIT 200
        """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _to_iso_date(date_str):
    """แปลงวันที่ DD/MM/YYYY หรือ YYYY-MM-DD ให้เป็น YYYY-MM-DD"""
    if not date_str:
        return None
    date_str = date_str.strip()
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return date_str

def get_requisitions_advanced(start_date=None, end_date=None, customer=None, keyword=None, status=None, limit=200):
    """
    ค้นหาใบเบิกขั้นสูง กรองตามช่วงวันที่, ชื่อลูกค้า, คำค้นหา, และสถานะ
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    # แปลงวันที่ช่วงค้นหาเป็น ISO (YYYY-MM-DD)
    iso_start = _to_iso_date(start_date)
    iso_end = _to_iso_date(end_date)

    date_expr = "(substr(r.req_date, 7, 4) || '-' || substr(r.req_date, 4, 2) || '-' || substr(r.req_date, 1, 2))"

    if iso_start and iso_end:
        conditions.append(f"{date_expr} BETWEEN ? AND ?")
        params.extend([iso_start, iso_end])
    elif iso_start:
        conditions.append(f"{date_expr} >= ?")
        params.append(iso_start)
    elif iso_end:
        conditions.append(f"{date_expr} <= ?")
        params.append(iso_end)

    if customer and customer.strip() and customer.strip() != "ทั้งหมด":
        conditions.append("r.customer_name LIKE ?")
        params.append(f"%{customer.strip()}%")

    if keyword and keyword.strip():
        k = f"%{keyword.strip()}%"
        conditions.append("(r.req_no LIKE ? OR r.driver_name LIKE ? OR r.vehicle_plate LIKE ? OR r.customer_name LIKE ? OR r.ref_bill_no LIKE ?)")
        params.extend([k, k, k, k, k])

    if status and status.strip() and status.strip() != "ทั้งหมด":
        conditions.append("r.status = ?")
        params.append(status.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_clause = f"LIMIT {int(limit)}" if limit else ""

    sql = f"""
        SELECT r.*, 
               COUNT(ri.id) as item_count,
               SUM(ri.quantity) as total_units
        FROM requisitions r
        LEFT JOIN requisition_items ri ON r.id = ri.requisition_id
        {where_clause}
        GROUP BY r.id
        ORDER BY r.id DESC
        {limit_clause}
    """
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_today_requisitions_stats():
    """สรุปยอดใบเบิกของวันนี้ (จำนวนบิล และจำนวนลูกที่จ่ายสำเร็จ)"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(DISTINCT r.id) as total_bills,
            SUM(CASE WHEN r.status = 'COMPLETED' THEN ri.quantity ELSE 0 END) as completed_units,
            COUNT(DISTINCT CASE WHEN r.status = 'COMPLETED' THEN r.id ELSE NULL END) as completed_bills,
            COUNT(DISTINCT CASE WHEN r.status = 'CANCELLED' THEN r.id ELSE NULL END) as cancelled_bills
        FROM requisitions r
        LEFT JOIN requisition_items ri ON r.id = ri.requisition_id
        WHERE r.req_date = ?
    """, (today_str,))
    row = cursor.fetchone()
    conn.close()

    return {
        "today_date": today_str,
        "total_bills": row["total_bills"] or 0,
        "completed_bills": row["completed_bills"] or 0,
        "cancelled_bills": row["cancelled_bills"] or 0,
        "completed_units": row["completed_units"] or 0
    }

def get_customers_list():
    """ดึงรายชื่อลูกค้า/ร้านค้าที่มีในระบบสำหรับใส่ Dropdown กรองข้อมูล"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT customer_name FROM requisitions WHERE customer_name IS NOT NULL AND customer_name != '' AND customer_name != '-' ORDER BY customer_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [r["customer_name"] for r in rows]

def get_requisition_by_id(req_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requisitions WHERE id = ?", (req_id,))
    req = cursor.fetchone()
    if not req:
        conn.close()
        return None, []

    cursor.execute("SELECT * FROM requisition_items WHERE requisition_id = ? ORDER BY id ASC", (req_id,))
    items = cursor.fetchall()
    conn.close()
    return dict(req), [dict(i) for i in items]

def cancel_requisition(req_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status FROM requisitions WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("ไม่พบใบเบิกนี้")
        if row["status"] == "CANCELLED":
            raise ValueError("ใบเบิกนี้ถูกยกเลิกไปแล้ว")

        # อัปเดตสถานะเป็นยกเลิก
        cursor.execute("UPDATE requisitions SET status = 'CANCELLED' WHERE id = ?", (req_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_requisition(req_id, driver_name, vehicle_plate, customer_name, route_zone, ref_bill_no, purpose, req_items, req_date=None):
    """
    แก้ไขข้อมูลใบเบิกเดิม
    """
    if not req_items:
        raise ValueError("กรุณาเลือกรายการแบตเตอรี่อย่างน้อย 1 รายการ")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT req_no, status FROM requisitions WHERE id = ?", (req_id,))
        curr = cursor.fetchone()
        if not curr:
            raise ValueError("ไม่พบใบเบิกที่ต้องการแก้ไข")
        if curr["status"] == "CANCELLED":
            raise ValueError("ใบเบิกนี้ถูกยกเลิกไปแล้ว ไม่สามารถแก้ไขได้")

        req_no = curr["req_no"]

        # 1. ตรวจสอบจำนวนสำหรับรายการใหม่
        for it in req_items:
            qty = int(it.get("quantity", 0))
            if qty <= 0:
                raise ValueError(f"จำนวนเบิกสำหรับรุ่น {it.get('item_code')} ต้องมากกว่า 0")

        # 2. ลบรายการสินค้าเดิม แล้วบันทึกรายการสินค้าใหม่
        cursor.execute("DELETE FROM requisition_items WHERE requisition_id = ?", (req_id,))
        for it in req_items:
            qty = int(it["quantity"])
            cursor.execute("""
                INSERT INTO requisition_items (requisition_id, item_id, brand, item_code, item_name, capacity, unit, quantity, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (req_id, it.get("item_id"), it.get("brand", ""), it["item_code"], it["item_name"], it.get("capacity", ""), it.get("unit", "ลูก"), qty, it.get("remark", "")))

        # 5. อัปเดตหัวใบเบิก
        cursor.execute("""
            UPDATE requisitions 
            SET driver_name = ?, vehicle_plate = ?, customer_name = ?, route_zone = ?, ref_bill_no = ?, purpose = ?, req_date = COALESCE(?, req_date)
            WHERE id = ?
        """, (driver_name.strip(), vehicle_plate.strip(), customer_name.strip(), route_zone.strip(), ref_bill_no.strip(), purpose.strip(), req_date, req_id))

        conn.commit()
        return req_id, req_no

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
import shutil

def get_db_info():
    """ดึงข้อมูลสถานะของฐานข้อมูล SQLite"""
    from database.db import DB_FILE
    db_abs_path = os.path.abspath(DB_FILE)
    size_bytes = os.path.getsize(db_abs_path) if os.path.exists(db_abs_path) else 0
    size_kb = size_bytes / 1024

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM items")
    item_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM requisitions")
    req_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM requisitions WHERE status = 'COMPLETED'")
    completed_req_count = cursor.fetchone()[0]

    conn.close()

    return {
        "db_file": DB_FILE,
        "db_path": db_abs_path,
        "size_kb": f"{size_kb:.1f} KB",
        "item_count": item_count,
        "req_count": req_count,
        "completed_count": completed_req_count,
        "status": "เชื่อมต่อสมบูรณ์ (Connected)"
    }

def backup_database(destination_folder=None):
    """สำรองไฟล์ฐานข้อมูล SQLite พร้อมประทับเวลา"""
    if not destination_folder:
        destination_folder = "database_backups"
    os.makedirs(destination_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"inventory_backup_{timestamp}.db"
    backup_path = os.path.join(destination_folder, backup_filename)

    shutil.copy2(DB_FILE, backup_path)
    return os.path.abspath(backup_path)
