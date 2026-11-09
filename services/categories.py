"""หมวดสินค้า และการสรุปยอด (แบตนับเป็น "ลูก" ส่วนสินค้าอื่นนับเป็น "รายการ")"""

BATTERY = "แบตเตอรี่"
OTHER_CATEGORIES = ["อะไหล่", "ทั่วไป", "อุปกรณ์เสริม", "น้ำกลั่น/เคมี", "เครื่องมือ"]
ALL_CATEGORIES = [BATTERY] + OTHER_CATEGORIES


def item_category(item):
    """หมวดของรายการ: ใช้ค่าที่บันทึกไว้ ถ้าไม่มี (ข้อมูลเก่า) จึงเดาจากยี่ห้อ"""
    category = (item.get("category") or "").strip()
    if category:
        return category
    if item.get("item_id"):
        return BATTERY
    brand = (item.get("brand") or "").strip()
    name = (item.get("item_name") or "").strip()
    if brand in OTHER_CATEGORIES and not name.startswith(BATTERY):
        return brand
    return BATTERY


def is_battery(item):
    return item_category(item) == BATTERY


def summarize_items(items):
    """คืนค่า (จำนวนแบตรวมเป็นลูก, จำนวนรายการสินค้าอื่น)"""
    battery_units = 0
    other_lines = 0
    for item in items:
        if is_battery(item):
            battery_units += int(item.get("quantity") or 0)
        else:
            other_lines += 1
    return battery_units, other_lines


def format_totals(battery_units, other_lines):
    text = f"แบต {battery_units:,} ลูก"
    if other_lines:
        text += f" | อื่นๆ {other_lines:,} รายการ"
    return text


def count_breakdown(items):
    """
    ยอดสำหรับตรวจนับก่อนส่งของ: แบตรวมเป็นยอดเดียว (ลูก) ตามด้วยสินค้าอื่นแยกตามชื่อและหน่วย
    ชื่อและหน่วยเดียวกันหลายบรรทัดจะถูกรวมยอด เรียงตามลำดับที่ปรากฏในบิล
    คืนค่า [(ชื่อ, จำนวน, หน่วย), ...]
    """
    battery_units = 0
    has_battery = False
    others = {}
    for item in items:
        qty = int(item.get("quantity") or 0)
        if is_battery(item):
            has_battery = True
            battery_units += qty
            continue
        name = " ".join(str(item.get("item_name") or item.get("item_code") or "-").split())
        unit = str(item.get("unit") or "").strip()
        key = (name, unit)
        others[key] = others.get(key, 0) + qty
    rows = [(BATTERY, battery_units, "ลูก")] if has_battery else []
    rows.extend((name, qty, unit) for (name, unit), qty in others.items())
    return rows


def format_breakdown(rows, separator=" | ", max_name_len=None):
    parts = []
    for name, qty, unit in rows:
        if max_name_len and len(name) > max_name_len:
            name = name[:max_name_len - 2].rstrip() + ".."
        parts.append(f"{name} {qty:,} {unit}".strip())
    return separator.join(parts)
