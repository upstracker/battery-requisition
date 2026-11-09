import os
import sys
import subprocess
from fpdf import FPDF
from datetime import datetime

FONT_REGULAR = os.path.abspath("assets/fonts/Sarabun-Regular.ttf")
FONT_BOLD = os.path.abspath("assets/fonts/Sarabun-Bold.ttf")

class BatteryRequisitionPDF(FPDF):
    def __init__(self):
        # A5 Landscape: 210 x 148 mm
        super().__init__(orientation="landscape", unit="mm", format=(148, 210))
        self.set_auto_page_break(auto=False)
        self.set_margins(left=12, top=6, right=12)
        self.set_text_shaping(True)
        self.add_font("Sarabun", style="", fname=FONT_REGULAR)
        self.add_font("Sarabun", style="B", fname=FONT_BOLD)

def generate_requisition_pdf(req_data, items_data, settings=None, output_path=None):
    """
    สร้างไฟล์ PDF ใบเบิกและจ่ายแบตเตอรี่ขึ้นรถส่งของ ขนาด A5 แนวนอน
    พร้อมตารางตรวจสอบเทียบกับบิล และการจัดของขึ้นรถ
    """
    if len(items_data) > 15:
        raise ValueError("ใบเบิก A5 รองรับได้สูงสุด 15 รายการต่อบิล")

    if settings is None:
        settings = {
            "company_name": "บริษัท คลังแบตเตอรี่และบริการ จำกัด",
            "slip_title": "ใบเบิกและจ่ายสินค้าขึ้นรถส่งของ (BATTERY LOADING & DELIVERY SLIP)",
            "sign_role_1": "พนักงานขับรถ / ผู้รับของขึ้นรถ",
            "sign_role_2": "เจ้าหน้าที่จัดจ่ายคลังสินค้า",
            "sign_role_3": "ผู้อนุมัติ / หัวหน้าคลัง",
        }

    if not output_path:
        os.makedirs("output_pdfs", exist_ok=True)
        safe_req_no = req_data.get("req_no", "REQ").replace("/", "-")
        output_path = os.path.join("output_pdfs", f"{safe_req_no}.pdf")

    pdf = BatteryRequisitionPDF()
    pdf.add_page()

    # --- ส่วนหัว (HEADER) ---
    pdf.set_y(6)
    pdf.set_font("Sarabun", style="B", size=12)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(w=115, h=5, text=settings.get("company_name", ""), new_x="RIGHT", new_y="TOP")

    # ป้ายเลขที่ใบเบิกมุมขวาบน
    pdf.set_font("Sarabun", style="B", size=11.5)
    pdf.set_text_color(14, 116, 144)
    pdf.cell(w=71, h=5, text=f"เลขที่: {req_data.get('req_no', '')}", align="R", new_x="LMARGIN", new_y="NEXT")

    # ชื่อเอกสาร
    pdf.set_font("Sarabun", style="B", size=13.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(w=186, h=6, text=settings.get("slip_title", "ใบเบิกและจ่ายสินค้าขึ้นรถส่งของ"), align="C", new_x="LMARGIN", new_y="NEXT")

    # เส้นคั่นหัวเรื่อง
    pdf.set_draw_color(14, 116, 144)
    pdf.set_line_width(0.5)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(1.5)

    # --- กล่องข้อมูลการจัดส่ง & รถส่งของ (DELIVERY INFO BOX) ---
    box_x = 12
    box_y = pdf.get_y()
    pdf.set_draw_color(203, 213, 225)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_line_width(0.2)
    pdf.rect(box_x, box_y, 186, 12, style="FD")

    # บรรทัดที่ 1: ทะเบียนรถ, คนขับ, บิลอ้างอิง, วันที่
    pdf.set_xy(box_x + 3, box_y + 1)
    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(18, 4, "ทะเบียนรถ:")
    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(32, 4, str(req_data.get("vehicle_plate", "-")))

    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(23, 4, "คนขับ/ผู้เบิก:")
    pdf.set_font("Sarabun", style="", size=9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(42, 4, str(req_data.get("driver_name", "-")))

    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(16, 4, "บิลอ้างอิง:")
    pdf.set_font("Sarabun", style="", size=9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(24, 4, str(req_data.get("ref_bill_no", "-")))

    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(11, 4, "วันที่:")
    pdf.set_font("Sarabun", style="", size=9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(20, 4, str(req_data.get("req_date", "-")), new_x="LMARGIN", new_y="NEXT")

    # บรรทัดที่ 2: ลูกค้า/ร้านค้า, สายส่ง/โซน, หมายเหตุ
    pdf.set_x(box_x + 3)
    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(20, 4, "ลูกค้า/ร้านค้า:")
    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(55, 4, str(req_data.get("customer_name", "-")))

    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(20, 4, "สายส่ง/โซน:")
    pdf.set_font("Sarabun", style="", size=9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(40, 4, str(req_data.get("route_zone", "-")))

    pdf.set_font("Sarabun", style="B", size=9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(16, 4, "หมายเหตุ:")
    pdf.set_font("Sarabun", style="", size=9.5)
    pdf.set_text_color(15, 23, 42)
    purpose_str = str(req_data.get("purpose", "-"))
    if len(purpose_str) > 28:
        purpose_str = purpose_str[:26] + ".."
    pdf.cell(35, 4, purpose_str)

    pdf.set_y(box_y + 13)

    # --- ตารางรายการแบตเตอรี่ (ITEMS TABLE WITH CHECKLIST) ---
    # ตัดคอลัมน์ "ยี่ห้อ / รหัสรุ่น" ออก และเพิ่มพื้นที่ให้รายละเอียดสินค้า
    col_w = [9, 83, 15, 13, 18, 18, 30]  # รวม 186 mm
    headers = [
        "ลำดับ", 
        "รายละเอียดแบตเตอรี่ / ขนาด (Ah)", 
        "จำนวน", 
        "หน่วย", 
        "ตรงบิล [ ]", 
        "ขึ้นรถ [ ]", 
        "หมายเหตุ"
    ]

    pdf.set_font("Sarabun", style="B", size=8)
    pdf.set_fill_color(226, 232, 240)
    pdf.set_text_color(30, 41, 59)
    pdf.set_draw_color(180, 190, 200)

    for i, h in enumerate(headers):
        align = "C"
        if i == 1:
            align = "L"
        pdf.cell(col_w[i], 4.8, h, border=1, align=align, fill=True)
    pdf.ln()

    # ข้อมูลสินค้า (บังคับ 15 แถวต่อบิล A5)
    pdf.set_font("Sarabun", style="", size=8)
    pdf.set_text_color(20, 20, 20)

    total_qty = 0
    max_display_rows = 15
    row_count = max_display_rows
    row_height = 3.9

    for idx in range(row_count):
        fill_bg = (idx % 2 == 1)
        if fill_bg:
            pdf.set_fill_color(250, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)

        if idx < len(items_data):
            item = items_data[idx]
            qty = int(item.get("quantity", 0))
            total_qty += qty
            no_text = str(idx + 1)
            name_text = str(item.get("item_name", ""))
            if len(name_text) > 62:
                name_text = name_text[:60] + ".."
            qty_text = f"{qty:,}"
            unit_text = str(item.get("unit", "ลูก"))
            remark_text = str(item.get("remark", ""))
            show_check = True
        else:
            no_text = ""
            name_text = ""
            qty_text = ""
            unit_text = ""
            remark_text = ""
            show_check = False

        row_y = pdf.get_y()
        pdf.cell(col_w[0], row_height, no_text, border="LR", align="C", fill=True)
        pdf.cell(col_w[1], row_height, f" {name_text}", border="LR", align="L", fill=True)
        pdf.cell(col_w[2], row_height, qty_text, border="LR", align="R", fill=True)
        pdf.cell(col_w[3], row_height, unit_text, border="LR", align="C", fill=True)

        # ช่องสี่เหลี่ยมสำหรับติ๊ก 'ตรงกับบิล'
        pdf.cell(col_w[4], row_height, "", border="LR", align="C", fill=True)
        if show_check:
            pdf.set_draw_color(100, 116, 139)
            pdf.rect(12 + sum(col_w[:4]) + 7.6, row_y + 0.55, 2.8, 2.8)

        # ช่องสี่เหลี่ยมสำหรับติ๊ก 'จัดขึ้นรถ'
        pdf.cell(col_w[5], row_height, "", border="LR", align="C", fill=True)
        if show_check:
            pdf.set_draw_color(100, 116, 139)
            pdf.rect(12 + sum(col_w[:5]) + 7.6, row_y + 0.55, 2.8, 2.8)

        pdf.cell(col_w[6], row_height, remark_text, border="LR", align="C", fill=True)
        pdf.ln()

    # แถวสรุปรวมท้ายตาราง
    pdf.set_font("Sarabun", style="B", size=9)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(180, 190, 200)
    merged_w = sum(col_w[:2])
    pdf.cell(merged_w, 4.8, "รวมจำนวนแบตเตอรี่ทั้งสิ้น (Total Units)", border=1, align="R", fill=True)
    pdf.cell(col_w[2], 4.8, f"{total_qty:,}", border=1, align="R", fill=True)
    pdf.cell(col_w[3], 4.8, "ลูก", border=1, align="C", fill=True)
    pdf.cell(col_w[4] + col_w[5] + col_w[6], 4.8, f"{len(items_data)} รายการ", border=1, align="C", fill=True)
    pdf.ln(5.6)

    # --- กล่องตรวจเช็คความถูกต้องก่อนปล่อยรถ (DISPATCH CHECKLIST BOX) ---
    check_box_y = pdf.get_y()
    pdf.set_draw_color(14, 116, 144)
    pdf.set_fill_color(240, 253, 250)
    pdf.set_line_width(0.3)
    pdf.rect(12, check_box_y, 186, 14, style="FD")

    # แถบหัวข้อกล่องเช็ค
    pdf.set_xy(15, check_box_y + 0.5)
    pdf.set_font("Sarabun", style="B", size=8)
    pdf.set_text_color(14, 116, 144)
    pdf.cell(180, 3, "ตารางตรวจเช็คความถูกต้องก่อนปล่อยรถ (DISPATCH & LOADING CHECKLIST)", new_x="LMARGIN", new_y="NEXT")

    # เช็คลิสต์ข้อ 1: ตรงกับบิล
    pdf.set_xy(16, check_box_y + 3.6)
    pdf.set_draw_color(14, 116, 144)
    pdf.rect(16, check_box_y + 3.8, 2.6, 2.6) # กล่องติ๊ก
    pdf.set_x(21)
    pdf.set_font("Sarabun", style="", size=7.2)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(170, 3, "[  ] 1. ตรวจเทียบกับบิล: ตรวจสอบรายการ ยี่ห้อ รุ่น และจำนวนลูก 'ตรงกับบิลขาย / ใบส่งของ' ครบถ้วนทุกรายการ")

    # เช็คลิสต์ข้อ 2: จัดของขึ้นรถ
    pdf.set_xy(16, check_box_y + 6.8)
    pdf.rect(16, check_box_y + 7, 2.6, 2.6) # กล่องติ๊ก
    pdf.set_x(21)
    pdf.cell(170, 3, "[  ] 2. ตรวจเทียบของขึ้นรถ: แบตเตอรี่ที่จัดยกขึ้นท้ายรถ 'ตรงกับใบเบิก' และตรวจสภาพตัวลูกสมบูรณ์ ไม่แตกรั่วซึม")

    # บรรทัดผู้ตรวจเช็ค & เวลาปล่อยรถ
    pdf.set_xy(16, check_box_y + 10.2)
    pdf.set_font("Sarabun", style="B", size=7.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(33, 3, "เจ้าหน้าที่ตรวจปล่อยรถ:")
    pdf.set_font("Sarabun", style="", size=7.5)
    pdf.cell(62, 3, "ลงชื่อ ..............................................................")

    pdf.set_font("Sarabun", style="B", size=7.5)
    pdf.cell(22, 3, "เวลาปล่อยรถ:")
    pdf.set_font("Sarabun", style="", size=7.5)
    pdf.cell(60, 3, "........... : ........... น.  ( รถพร้อมออกเดินทาง )")

    pdf.set_y(check_box_y + 15)

    # --- ส่วนลงชื่อ 3 ช่องท้ายเอกสาร (SIGNATURES) ---
    sig_w = 58
    sig_gap = 6
    roles = [
        settings.get("sign_role_1", "พนักงานขับรถ / ผู้รับของขึ้นรถ"),
        settings.get("sign_role_2", "เจ้าหน้าที่จัดจ่ายคลังสินค้า"),
        settings.get("sign_role_3", "ผู้อนุมัติ / หัวหน้าคลัง")
    ]
    driver_val = req_data.get("driver_name", "")

    start_x = 12
    curr_y = pdf.get_y()

    for idx, role in enumerate(roles):
        bx = start_x + idx * (sig_w + sig_gap)
        pdf.set_xy(bx, curr_y)

        pdf.set_draw_color(203, 213, 225)
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(bx, curr_y, sig_w, 22, style="D")

        # ชื่อบทบาท
        pdf.set_xy(bx, curr_y + 1)
        pdf.set_font("Sarabun", style="B", size=9)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(sig_w, 3.8, role, align="C")

        # บรรทัดเซ็น
        pdf.set_xy(bx, curr_y + 8.5)
        pdf.set_font("Sarabun", style="", size=8.5)
        pdf.cell(sig_w, 3.6, "ลงชื่อ .....................................................", align="C")

        # บรรทัดชื่อ
        pdf.set_xy(bx, curr_y + 13)
        name_placeholder = f"( {driver_val} )" if idx == 0 and driver_val and driver_val != "-" else "( ..................................................... )"
        pdf.cell(sig_w, 3.6, name_placeholder, align="C")

        # วันที่
        pdf.set_xy(bx, curr_y + 17.5)
        date_placeholder = f"วันที่ {req_data.get('req_date', '')}" if idx == 0 and req_data.get('req_date') else "วันที่ ......... / ......... / ................"
        pdf.cell(sig_w, 3.6, date_placeholder, align="C")

    # บันทึกไฟล์
    pdf.output(output_path)
    return output_path

def open_pdf_file(pdf_path):
    if not os.path.exists(pdf_path):
        return
    if sys.platform.startswith("win"):
        os.startfile(pdf_path)
    elif sys.platform.startswith("darwin"):
        subprocess.run(["open", pdf_path], check=False)
    else:
        subprocess.run(["xdg-open", pdf_path], check=False)

if __name__ == "__main__":
    sample_req = {
        "req_no": "BAT-202609-0001",
        "req_date": "03/09/2026",
        "driver_name": "นายประเสริฐ ขับดี",
        "vehicle_plate": "1ผข-4512 กทม.",
        "customer_name": "ร้านสหยนต์การช่าง (บางนา)",
        "route_zone": "สายส่งบางนา - สมุทรปราการ",
        "ref_bill_no": "SO-69012",
        "purpose": "ส่งรอบเช้า มีลูกเก่าเทิร์น 4 ลูก"
    }
    sample_items = [
        {"brand": "GS", "item_code": "MFX-60L", "item_name": "GS MFX-60L (50B24L) 45Ah กึ่งแห้ง ขั้ว L", "unit": "ลูก", "quantity": 4, "remark": "เก๋งเล็ก"},
        {"brand": "3K", "item_code": "MAX-X 105D31L", "item_name": "3K MAX-X 105D31L 90Ah ขั้ว L ไฮบริด", "unit": "ลูก", "quantity": 6, "remark": "กระบะ"},
        {"brand": "FB", "item_code": "GOLD 55D23L", "item_name": "FB PREMIUM GOLD 55D23L 60Ah แบตแห้ง", "unit": "ลูก", "quantity": 2, "remark": "SMF"},
    ]
    path = generate_requisition_pdf(sample_req, sample_items)
    print("Generated:", path)
