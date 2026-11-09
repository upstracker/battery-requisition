import os
import sqlite3
from datetime import datetime

import app_paths
from database.db import REQ_NO_PATTERN, get_connection, generate_next_req_no, get_db_file, record_issued_req_no
from services.categories import BATTERY, item_category
from services.dates import normalize_req_date, to_iso_date
from services.errors import ConflictError

# ยอดรวมต่อใบเบิก: แบตนับเป็นลูก ส่วนสินค้าอื่นนับเป็นจำนวนรายการ (หน่วยต่างกัน รวมกันไม่ได้)
_TOTALS_SQL = f"""
    SUM(CASE WHEN ri.category = '{BATTERY}' THEN ri.quantity ELSE 0 END) AS battery_units,
    SUM(CASE WHEN ri.id IS NOT NULL AND ri.category != '{BATTERY}' THEN 1 ELSE 0 END) AS other_lines
"""


def next_req_no():
    """เลขที่ใบเบิกถัดไป (เครื่องลูกเรียกผ่านเครื่องหลัก)"""
    return generate_next_req_no()


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


def get_item_by_code(item_code):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE item_code = ?", (item_code.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_item(brand, item_code, item_name, capacity="45 Ah", battery_type="กึ่งแห้ง (MF)", unit="ลูก", stock_qty=0, min_qty=5, category=BATTERY):
    """เพิ่มรุ่นสินค้าลงข้อมูลรุ่น คืนค่า id ของรายการใหม่"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO items (brand, item_code, item_name, capacity, battery_type, unit, stock_qty, min_qty, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (brand.strip(), item_code.strip(), item_name.strip(), capacity.strip(), battery_type.strip(), unit.strip(), int(stock_qty), int(min_qty), category))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_item(item_id, brand, item_code, item_name, capacity, battery_type, unit, stock_qty, min_qty):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE items
            SET brand = ?, item_code = ?, item_name = ?, capacity = ?, battery_type = ?, unit = ?, stock_qty = ?, min_qty = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (brand.strip(), item_code.strip(), item_name.strip(), capacity.strip(), battery_type.strip(), unit.strip(), int(stock_qty), int(min_qty), item_id))
        conn.commit()
    finally:
        conn.close()


def delete_item(item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def _validate_items(req_items):
    if not req_items:
        raise ValueError("กรุณาเลือกรายการแบตเตอรี่อย่างน้อย 1 รายการ")
    for it in req_items:
        qty = int(it.get("quantity", 0))
        if qty <= 0:
            raise ValueError(f"จำนวนเบิกสำหรับรุ่น {it.get('item_code')} ต้องมากกว่า 0")


def _insert_requisition_items(cursor, req_id, req_items):
    for it in req_items:
        cursor.execute("""
            INSERT INTO requisition_items (requisition_id, item_id, brand, item_code, item_name, capacity, unit, quantity, remark, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req_id, it.get("item_id"), it.get("brand", ""), it["item_code"], it["item_name"],
            it.get("capacity", ""), it.get("unit", "ลูก"), int(it["quantity"]), it.get("remark", ""),
            item_category(it),
        ))


def create_requisition(driver_name, vehicle_plate, customer_name, route_zone, ref_bill_no, purpose, req_items, custom_req_no=None, req_date=None):
    """สร้างใบเบิกแบตเตอรี่ขึ้นรถส่งของ (ไม่มีการตัดสต็อก)"""
    _validate_items(req_items)
    final_date = normalize_req_date(req_date) if req_date else datetime.now().strftime("%d/%m/%Y")
    final_req_no = (custom_req_no or "").strip() or generate_next_req_no()

    # เลขที่ที่ระบบออกให้ (รูปแบบ REQ-YYYYMM-NNNN) ถ้าชนกับของเครื่องอื่นที่เพิ่งบันทึก จะขยับเป็นเลขถัดไปให้เอง
    auto_numbered = bool(REQ_NO_PATTERN.match(final_req_no))

    conn = get_connection()
    cursor = conn.cursor()
    try:
        for _ in range(8):
            try:
                cursor.execute("""
                    INSERT INTO requisitions (req_no, req_date, driver_name, vehicle_plate, customer_name, route_zone, ref_bill_no, purpose, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED')
                """, (final_req_no, final_date, driver_name.strip(), vehicle_plate.strip(), customer_name.strip(), route_zone.strip(), ref_bill_no.strip(), purpose.strip()))
                break
            except sqlite3.IntegrityError:
                if not auto_numbered:
                    raise ValueError(f"เลขที่ใบเบิก {final_req_no} มีอยู่ในระบบแล้ว กรุณาใช้เลขอื่น") from None
                final_req_no = generate_next_req_no()
        else:
            raise ValueError("ออกเลขที่ใบเบิกไม่สำเร็จ กรุณาลองกดบันทึกอีกครั้ง")
        req_id = cursor.lastrowid
        _insert_requisition_items(cursor, req_id, req_items)
        record_issued_req_no(cursor, final_req_no)
        conn.commit()
        return req_id, final_req_no
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _build_filter(start_date=None, end_date=None, customer=None, keyword=None, status=None):
    conditions = []
    params = []

    iso_start = to_iso_date(start_date)
    iso_end = to_iso_date(end_date)
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
    return where_clause, params


def get_requisitions_advanced(start_date=None, end_date=None, customer=None, keyword=None, status=None, limit=None):
    """
    ค้นหาใบเบิกตามช่วงวันที่ (DD/MM/YYYY ค.ศ. หรือ พ.ศ.), ลูกค้า, คำค้น และสถานะ
    limit=None คืนทุกใบที่ตรงเงื่อนไข (ใช้คำนวณยอดสรุปและส่งออก Excel)
    """
    where_clause, params = _build_filter(start_date, end_date, customer, keyword, status)
    limit_clause = f"LIMIT {int(limit)}" if limit else ""

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT r.*, COUNT(ri.id) AS item_count, {_TOTALS_SQL}
        FROM requisitions r
        LEFT JOIN requisition_items ri ON r.id = ri.requisition_id
        {where_clause}
        GROUP BY r.id
        ORDER BY r.id DESC
        {limit_clause}
    """, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_requisitions_stats():
    """สรุปยอดใบเบิกของวันนี้"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT
            COUNT(DISTINCT r.id) AS total_bills,
            SUM(CASE WHEN r.status = 'COMPLETED' AND ri.category = '{BATTERY}' THEN ri.quantity ELSE 0 END) AS completed_units,
            SUM(CASE WHEN r.status = 'COMPLETED' AND ri.id IS NOT NULL AND ri.category != '{BATTERY}' THEN 1 ELSE 0 END) AS completed_other_lines,
            COUNT(DISTINCT CASE WHEN r.status = 'COMPLETED' THEN r.id ELSE NULL END) AS completed_bills,
            COUNT(DISTINCT CASE WHEN r.status = 'CANCELLED' THEN r.id ELSE NULL END) AS cancelled_bills
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
        "completed_units": row["completed_units"] or 0,
        "completed_other_lines": row["completed_other_lines"] or 0,
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

        cursor.execute("UPDATE requisitions SET status = 'CANCELLED', version = version + 1 WHERE id = ?", (req_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_requisition(req_id):
    """ลบใบเบิกถาวร (รายการสินค้าในใบถูกลบตามด้วย ON DELETE CASCADE) เลขที่ใบเบิกจะไม่ถูกนำกลับมาใช้"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT req_no FROM requisitions WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("ไม่พบใบเบิกนี้")
        record_issued_req_no(cursor, row["req_no"])
        cursor.execute("DELETE FROM requisitions WHERE id = ?", (req_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_cancelled_requisitions():
    """ลบใบเบิกที่สถานะยกเลิกทั้งหมด คืนค่าจำนวนใบที่ลบ"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT req_no FROM requisitions WHERE status = 'CANCELLED'")
        for row in cursor.fetchall():
            record_issued_req_no(cursor, row["req_no"])
        cursor.execute("DELETE FROM requisitions WHERE status = 'CANCELLED'")
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_requisition(req_id, driver_name, vehicle_plate, customer_name, route_zone, ref_bill_no, purpose, req_items, req_date=None, expected_version=None):
    """แก้ไขข้อมูลใบเบิกเดิม ถ้าส่ง expected_version มา และใบถูกแก้โดยเครื่องอื่นไปแล้ว จะไม่เขียนทับ"""
    _validate_items(req_items)
    final_date = normalize_req_date(req_date) if req_date else None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT req_no, status, version FROM requisitions WHERE id = ?", (req_id,))
        curr = cursor.fetchone()
        if not curr:
            raise ValueError("ไม่พบใบเบิกที่ต้องการแก้ไข (อาจถูกลบโดยเครื่องอื่นแล้ว)")
        if expected_version is not None and curr["version"] != expected_version:
            raise ConflictError(
                f"ใบเบิก {curr['req_no']} ถูกแก้ไขหรือยกเลิกโดยเครื่องอื่นไปแล้ว ไม่เขียนทับให้\n"
                "กรุณากด 'ยกเลิกการแก้ไข' แล้วเปิดใบนี้จากหน้าประวัติใหม่อีกครั้ง"
            )
        if curr["status"] == "CANCELLED":
            raise ValueError("ใบเบิกนี้ถูกยกเลิกไปแล้ว ไม่สามารถแก้ไขได้")

        req_no = curr["req_no"]

        cursor.execute("DELETE FROM requisition_items WHERE requisition_id = ?", (req_id,))
        _insert_requisition_items(cursor, req_id, req_items)

        cursor.execute("""
            UPDATE requisitions
            SET driver_name = ?, vehicle_plate = ?, customer_name = ?, route_zone = ?, ref_bill_no = ?, purpose = ?, req_date = COALESCE(?, req_date), version = version + 1
            WHERE id = ?
        """, (driver_name.strip(), vehicle_plate.strip(), customer_name.strip(), route_zone.strip(), ref_bill_no.strip(), purpose.strip(), final_date, req_id))

        conn.commit()
        return req_id, req_no
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_info():
    """ดึงข้อมูลสถานะของฐานข้อมูล SQLite"""
    db_abs_path = os.path.abspath(get_db_file())
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
        "db_file": db_abs_path,
        "db_path": db_abs_path,
        "size_kb": f"{size_kb:.1f} KB",
        "item_count": item_count,
        "req_count": req_count,
        "completed_count": completed_req_count,
        "status": "เชื่อมต่อสมบูรณ์ (Connected)"
    }


def backup_database(destination_folder=None):
    """สำรองไฟล์ฐานข้อมูล SQLite พร้อมประทับเวลา (ใช้ backup API ให้ได้ข้อมูลครบแม้อยู่ในโหมด WAL)"""
    destination_folder = destination_folder or app_paths.backup_dir()
    os.makedirs(destination_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(destination_folder, f"inventory_backup_{timestamp}.db")

    src = get_connection()
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return os.path.abspath(backup_path)
