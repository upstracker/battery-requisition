"""กฎการแยกยี่ห้อและสร้างรหัสรุ่นจากชื่อแบตเตอรี่ (ใช้ร่วมกันระหว่างตัวนำเข้า Excel และ migration)"""
import re

BRANDS = [
    "GLOBAL POWER", "SCHAEFFLER", "POWERZONE", "AMARON", "BOLIDEN",
    "PINACO", "SOLITE", "BOSCH", "VARTA", "YUASA", "NIKO", "ULTRA",
    "ROCKET", "PUMA", "LONG", "BMF", "ESB", "FB", "GS", "RR",
]

UNKNOWN_BRAND = "ทั่วไป"


def _brand_pattern(brand):
    # ยี่ห้อต้องเป็นคำเดี่ยว: "EFB" หรือ "12FB" ต้องไม่ถูกนับเป็น FB
    return re.compile(r"(?<![A-Z0-9])" + re.escape(brand) + r"(?![A-Z0-9])")


_BRAND_PATTERNS = [(b, _brand_pattern(b)) for b in BRANDS]


def detect_brand(raw):
    """เลือกยี่ห้อที่ปรากฏเป็นคำแรกสุดในชื่อ ถ้าตำแหน่งเท่ากันเลือกชื่อที่ยาวกว่า"""
    text = str(raw or "").upper()
    best = None
    for brand, pattern in _BRAND_PATTERNS:
        match = pattern.search(text)
        if match and (best is None or (match.start(), -len(brand)) < (best[0], -len(best[1]))):
            best = (match.start(), brand)
    return best[1] if best else UNKNOWN_BRAND


def clean_model_code(raw, brand):
    text = str(raw or "")
    text = re.sub(r"^(?:BATTERY|แบตเตอรี่|ยี่ห้อ)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(brand) + r"(?![A-Za-z0-9])", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(?:รุ่น|แบบ)\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text).strip(" -_/")
    if not text:
        text = str(raw or "")[:30]
    return text


def build_base_code(raw, brand):
    model = clean_model_code(raw, brand)
    if len(model) > 40:
        model = model[:38] + ".."
    if model.upper().startswith(brand.upper()):
        return model
    return f"{brand} {model}".strip()
