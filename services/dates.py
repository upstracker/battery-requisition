"""วันที่ใบเบิก: รับหลายรูปแบบ แต่จัดเก็บเป็น DD/MM/YYYY (ปี ค.ศ.) เสมอ"""
import re
from datetime import date

BUDDHIST_OFFSET = 543
_DMY = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\s*$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")


def parse_req_date(text):
    """แปลงข้อความเป็น date รองรับ 3/9/2026, 03-09-2026, 3/9/2569 (พ.ศ.), 2026-09-03"""
    raw = str(text or "").strip()
    m = _DMY.match(raw)
    if m:
        day, month, year = (int(g) for g in m.groups())
    else:
        m = _ISO.match(raw)
        if not m:
            raise ValueError(f"รูปแบบวันที่ไม่ถูกต้อง: '{raw}' (ตัวอย่างที่ถูกต้อง: 03/09/2026)")
        year, month, day = (int(g) for g in m.groups())
    if year > 2400:
        year -= BUDDHIST_OFFSET
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"ไม่มีวันที่นี้ในปฏิทิน: '{raw}'") from None


def normalize_req_date(text):
    return parse_req_date(text).strftime("%d/%m/%Y")


def to_iso_date(text):
    """สำหรับตัวกรองวันที่: ช่องว่างคืนค่า None"""
    if not str(text or "").strip():
        return None
    return parse_req_date(text).isoformat()
