import os
import re
import tkinter as tk
from tkinter import messagebox, ttk
import customtkinter as ctk
from datetime import datetime, timedelta
from PIL import Image, ImageTk

import app_paths
from database.db import init_db, generate_next_req_no
from services import inventory_service as inv_service
from services import pdf_generator as pdf_gen
from services import report_export as report_exporter
from services.battery_search import (
    find_inventory_matches,
    parse_battery_quick_entry,
    pick_direct_match,
    prepare_inventory_items_for_search
)
from services.categories import (
    BATTERY,
    OTHER_CATEGORIES,
    count_breakdown,
    format_breakdown,
    format_totals,
    is_battery,
    item_category,
)
from services.catalog_rules import detect_brand
from services.dates import normalize_req_date

HISTORY_DISPLAY_LIMIT = 500
BATTERY_TYPES = ["ไม่ระบุ", "กึ่งแห้ง (MF)", "แห้ง (SMF)", "EFB", "AGM", "น้ำ (Conventional)", "ไฮบริด"]
UNIT_CHOICES = ["ลูก", "ตัว", "อัน", "ชิ้น", "ตลับ", "ชุด", "กล่อง", "ขวด", "แกลลอน", "ลัง"]

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class BatteryRequisitionApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ระบบออกใบเบิกจ่ายแบตเตอรี่ขึ้นรถส่งของ (A5 Landscape)")
        self.geometry("1260x780")
        self.minsize(1080, 680)

        # เริ่มต้นฐานข้อมูล
        init_db()

        self.editing_req_id = None # เก็บ ID ใบเบิกที่กำลังแก้ไขอยู่ (None = สร้างใหม่)
        self.cart_items = []
        self.all_inventory_items = []
        self.cart_qty_entries = []
        self.cart_rem_entries = []
        self.cart_name_entries = []
        self.current_matches = []
        self.current_scored_matches = []
        self.match_selection_moved = False
        self.matches_query = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        # โหลดภาพไอคอนแบตเตอรี่รถยนต์ (12V Car Battery Icon)
        car_battery_icon_path = app_paths.asset_file("car_battery.png")
        self.img_car_battery_logo = None
        self.img_car_battery_btn = None
        if os.path.exists(car_battery_icon_path):
            try:
                pil_icon = Image.open(car_battery_icon_path)
                self.img_car_battery_logo = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(38, 38))
                self.img_car_battery_btn = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(22, 22))
                self.tk_app_icon = ImageTk.PhotoImage(pil_icon)
                self.iconphoto(False, self.tk_app_icon)
            except Exception:
                pass

        self.create_sidebar()

        self.main_container = ctk.CTkFrame(self, corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.frames["req"] = self.create_requisition_view()
        self.frames["stock"] = self.create_stock_view()
        self.frames["history"] = self.create_history_view()
        self.frames["settings"] = self.create_settings_view()

        self.show_frame("req")

        # ผูกปุ่มลัดคีย์บอร์ดสำหรับการคีย์ด่วน
        self.bind("<F2>", lambda e: self.focus_quick_search())
        self.bind("<F3>", lambda e: self.focus_first_cart_qty())
        self.bind("<Control-s>", lambda e: self.save_and_print_pdf())
        self.bind("<Command-s>", lambda e: self.save_and_print_pdf())

        # เริ่มต้นเปิดโปรแกรมแบบเต็มจอ (Maximized)
        try:
            self.state("zoomed")
        except Exception:
            pass
        self.after(50, self._ensure_maximized)

    def _ensure_maximized(self):
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                try:
                    sw = self.winfo_screenwidth()
                    sh = self.winfo_screenheight()
                    self.geometry(f"{sw}x{sh}+0+0")
                except Exception:
                    pass

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=14, pady=(20, 16))

        if self.img_car_battery_logo:
            self.logo_icon = ctk.CTkLabel(
                logo_frame, 
                text="", 
                image=self.img_car_battery_logo
            )
            self.logo_icon.pack(side="top", pady=(0, 6))

        logo_label = ctk.CTkLabel(
            logo_frame, 
            text="คลังแบตเตอรี่\nจ่ายของขึ้นรถ (A5)", 
            font=ctk.CTkFont(family="Sarabun", size=16, weight="bold"),
            justify="center"
        )
        logo_label.pack(side="top")

        self.btn_nav_req = ctk.CTkButton(
            self.sidebar, text="📝 เบิกจ่ายขึ้นรถส่งของ",
            font=ctk.CTkFont(family="Sarabun", size=14),
            height=40, anchor="w",
            command=lambda: self.show_frame("req")
        )
        self.btn_nav_req.grid(row=1, column=0, padx=14, pady=6, sticky="ew")

        if self.img_car_battery_btn:
            self.btn_nav_stock = ctk.CTkButton(
                self.sidebar, text="  ข้อมูลรุ่นแบตเตอรี่",
                image=self.img_car_battery_btn,
                compound="left",
                font=ctk.CTkFont(family="Sarabun", size=14),
                height=40, anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
                command=lambda: self.show_frame("stock")
            )
        else:
            self.btn_nav_stock = ctk.CTkButton(
                self.sidebar, text="🚗 ข้อมูลรุ่นแบตเตอรี่",
                font=ctk.CTkFont(family="Sarabun", size=14),
                height=40, anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
                command=lambda: self.show_frame("stock")
            )
        self.btn_nav_stock.grid(row=2, column=0, padx=14, pady=6, sticky="ew")

        self.btn_nav_hist = ctk.CTkButton(
            self.sidebar, text="📋 ประวัติและพิมพ์ซ้ำ",
            font=ctk.CTkFont(family="Sarabun", size=14),
            height=40, anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            command=lambda: self.show_frame("history")
        )
        self.btn_nav_hist.grid(row=3, column=0, padx=14, pady=6, sticky="ew")

        self.btn_nav_sett = ctk.CTkButton(
            self.sidebar, text="⚙️ ตั้งค่าหัวเอกสาร",
            font=ctk.CTkFont(family="Sarabun", size=14),
            height=40, anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            command=lambda: self.show_frame("settings")
        )
        self.btn_nav_sett.grid(row=4, column=0, padx=14, pady=6, sticky="ew")

        # ป้ายสถานะ SQLite
        db_badge = ctk.CTkLabel(
            self.sidebar, text="🟢 ฐานข้อมูล: SQLite (.db)", 
            font=ctk.CTkFont(size=11, weight="bold"), 
            text_color="#10b981"
        )
        db_badge.grid(row=5, column=0, padx=18, pady=(12, 0), sticky="w")

        theme_label = ctk.CTkLabel(self.sidebar, text="ธีมการแสดงผล:", font=ctk.CTkFont(size=12))
        theme_label.grid(row=6, column=0, padx=18, pady=(10, 0), sticky="w")
        self.theme_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["System", "Light", "Dark"],
            command=ctk.set_appearance_mode,
            height=30
        )
        self.theme_menu.grid(row=7, column=0, padx=18, pady=(5, 20), sticky="ew")

    def show_frame(self, name):
        buttons = {
            "req": self.btn_nav_req,
            "stock": self.btn_nav_stock,
            "history": self.btn_nav_hist,
            "settings": self.btn_nav_sett
        }
        for k, btn in buttons.items():
            if k == name:
                btn.configure(fg_color=["#0e7490", "#0891b2"], text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))

        for frame in self.frames.values():
            frame.grid_forget()
        self.frames[name].grid(row=0, column=0, sticky="nsew")

        if name == "req":
            if not self.editing_req_id:
                self.refresh_req_screen()
        elif name == "stock":
            self.refresh_stock_table()
        elif name == "history":
            self.refresh_history_table()
        elif name == "settings":
            self.load_settings()

    # ==========================================
    # 1. VIEW: เบิกจ่ายแบตเตอรี่ขึ้นรถส่งของ
    # ==========================================
    def create_requisition_view(self):
        view = ctk.CTkFrame(self.main_container, corner_radius=0, fg_color="transparent")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)

        # แถบแสดงสถานะโหมดแก้ไขใบเบิก
        self.edit_banner_frame = ctk.CTkFrame(view, fg_color=("#fef3c7", "#78350f"), corner_radius=8)
        self.lbl_edit_banner = ctk.CTkLabel(
            self.edit_banner_frame, 
            text="🔧 โหมดแก้ไขใบเบิก: REQ-XXXXXX", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#92400e", "#fde68a")
        )
        self.lbl_edit_banner.pack(side="left", padx=14, pady=8)

        btn_cancel_edit = ctk.CTkButton(
            self.edit_banner_frame, 
            text="✖ ยกเลิกการแก้ไข / กลับหน้าปกติ", 
            fg_color="#ef4444", hover_color="#dc2626",
            height=28, width=190,
            command=self.exit_edit_mode
        )
        btn_cancel_edit.pack(side="right", padx=14, pady=8)

        # Container สำหรับ 2 คอลัมน์ (ซ้าย/ขวา) - สัดส่วน 4:6 (ขยายฝั่งขวา 60% ให้รายการจัดขึ้นรถใหญ่เด่นชัดเป็นพิเศษ)
        self.panels_container = ctk.CTkFrame(view, fg_color="transparent")
        self.panels_container.grid(row=1, column=0, sticky="nsew")
        self.panels_container.grid_columnconfigure(0, weight=4, uniform="panels")
        self.panels_container.grid_columnconfigure(1, weight=6, uniform="panels")
        self.panels_container.grid_rowconfigure(0, weight=1)

        # แผงซ้าย: กรอกข้อมูลขนส่งและเลือกแบตเตอรี่
        left_panel = ctk.CTkScrollableFrame(self.panels_container, corner_radius=10)
        left_panel.grid(row=0, column=0, padx=(14, 8), pady=14, sticky="nsew")
        left_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(left_panel, text="🚚 1. ข้อมูลรถส่งของและลูกค้า", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(4, 10)
        )

        ctk.CTkLabel(left_panel, text="เลขที่ใบเบิก:").grid(row=1, column=0, sticky="w", pady=3)
        self.entry_req_no = ctk.CTkEntry(left_panel)
        self.entry_req_no.grid(row=1, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="วันที่เบิก:").grid(row=2, column=0, sticky="w", pady=3)
        self.entry_req_date = ctk.CTkEntry(left_panel)
        self.entry_req_date.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.entry_req_date.grid(row=2, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="ทะเบียนรถส่ง:").grid(row=3, column=0, sticky="w", pady=3)
        self.entry_vehicle = ctk.CTkEntry(left_panel, placeholder_text="เช่น 1ผข-4512 กทม. (ไม่ระบุก็ได้)")
        self.entry_vehicle.grid(row=3, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="คนขับ/ผู้เบิก:").grid(row=4, column=0, sticky="w", pady=3)
        self.entry_driver = ctk.CTkEntry(left_panel, placeholder_text="ชื่อคนขับ / ผู้เบิก (ไม่ระบุก็ได้)")
        self.entry_driver.grid(row=4, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="ร้านค้า/ลูกค้า:*").grid(row=5, column=0, sticky="w", pady=3)
        self.entry_customer = ctk.CTkEntry(left_panel, placeholder_text="เช่น ร้านสหยนต์การช่าง, อู่ช่างเอก")
        self.entry_customer.grid(row=5, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="สายส่ง/โซน:").grid(row=6, column=0, sticky="w", pady=3)
        self.combo_route = ctk.CTkComboBox(left_panel, values=[
            "สายส่งบางนา - สมุทรปราการ",
            "สายส่งรังสิต - ปทุมธานี",
            "สายส่งพระราม 2 - มหาชัย",
            "สายส่งฝั่งธน - ราชพฤกษ์",
            "สายส่งในเมือง / ด่วน",
            "สายส่งต่างจังหวัด / ชลบุรี"
        ])
        self.combo_route.set("")
        self.combo_route.grid(row=6, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="บิลขายอ้างอิง:").grid(row=7, column=0, sticky="w", pady=3)
        self.entry_ref_bill = ctk.CTkEntry(left_panel, placeholder_text="เช่น SO-69012, INV-0881")
        self.entry_ref_bill.grid(row=7, column=1, sticky="ew", pady=3, padx=(8, 0))

        ctk.CTkLabel(left_panel, text="หมายเหตุการส่ง:").grid(row=8, column=0, sticky="w", pady=3)
        self.entry_purpose = ctk.CTkEntry(left_panel, placeholder_text="เช่น มีลูกเก่าเทิร์น 4 ลูก, ส่งก่อน 11:00")
        self.entry_purpose.grid(row=8, column=1, sticky="ew", pady=3, padx=(8, 0))

        sep = ctk.CTkFrame(left_panel, height=2, fg_color=("gray75", "gray30"))
        sep.grid(row=9, column=0, columnspan=2, sticky="ew", pady=12)

        # หัวข้อส่วนที่ 2: ค้นหาและเลือกรุ่นแบตเตอรี่ (Embedded Live Match Table)
        sec2_header = ctk.CTkFrame(left_panel, fg_color="transparent")
        sec2_header.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(2, 2))
        ctk.CTkLabel(sec2_header, text="⚡ 2. ค้นหาและเลือกรุ่นแบตเตอรี่", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self.btn_new_battery = ctk.CTkButton(
            sec2_header, text="➕ เพิ่มแบตรุ่นใหม่",
            fg_color="#0e7490", hover_color="#155e75",
            height=28, width=120, font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self.open_new_battery_dialog(),
        )
        self.btn_new_battery.pack(side="right")
        self.lbl_match_count = ctk.CTkLabel(sec2_header, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#0e7490")
        self.lbl_match_count.pack(side="right", padx=(6, 8))

        # ปุ่มลัดยี่ห้อยอดนิยม (Quick Brand Chips)
        brand_chips_frame = ctk.CTkScrollableFrame(left_panel, height=36, orientation="horizontal", fg_color="transparent")
        brand_chips_frame.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        
        top_brands = ["ทั้งหมด", "FB", "GS", "YUASA", "BOLIDEN", "AMARON", "SOLITE", "ESB", "VARTA", "SCHAEFFLER", "NIKO", "BOSCH"]
        self.brand_chip_buttons = {}
        self.selected_brand_chip = "ทั้งหมด"
        for b in top_brands:
            btn_chip = ctk.CTkButton(
                brand_chips_frame, text=b, width=48, height=26,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#0284c7" if b == "ทั้งหมด" else ("#e2e8f0", "#1e293b")),
                text_color=("white" if b == "ทั้งหมด" else ("#0f172a", "#f8fafc")),
                hover_color="#0369a1",
                command=lambda br=b: self.on_select_brand_chip(br)
            )
            btn_chip.pack(side="left", padx=2)
            self.brand_chip_buttons[b] = btn_chip

        # กล่องพิมพ์ค้นหาด่วน
        search_box_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        search_box_frame.grid(row=12, column=0, columnspan=2, sticky="ew", pady=2)
        search_box_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(search_box_frame, text="🔍 ค้นหารุ่น:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.entry_battery_search = ctk.CTkEntry(
            search_box_frame, 
            placeholder_text="พิมพ์ตัวเลข รุ่น หรือยี่ห้อ แล้วกด Enter เพื่อดูรายละเอียด...",
            height=34,
            font=ctk.CTkFont(size=13)
        )
        self.entry_battery_search.grid(row=0, column=1, sticky="ew")
        self.entry_battery_search.bind("<KeyRelease>", self.on_live_search_key)
        self.entry_battery_search.bind("<Return>", self.on_live_search_enter)
        self.entry_battery_search.bind("<Down>", self.on_live_search_down)
        self.entry_battery_search.bind("<Up>", self.on_live_search_up)
        self.entry_battery_search.bind("<Escape>", self.clear_live_search)

        # ตารางผลลัพธ์การค้นหาแบบสด (Live Matches Treeview)
        tree_container = ctk.CTkFrame(left_panel, corner_radius=6)
        tree_container.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        tree_container.grid_columnconfigure(0, weight=1)

        self.matches_tree = ttk.Treeview(
            tree_container,
            columns=("brand", "code", "capacity", "action"),
            show="headings",
            selectmode="browse",
            height=6
        )
        self.matches_tree.heading("brand", text="ยี่ห้อ")
        self.matches_tree.heading("code", text="รหัส / รุ่นแบตเตอรี่")
        self.matches_tree.heading("capacity", text="ความจุ")
        self.matches_tree.heading("action", text="ดับเบิลคลิกเพิ่ม")

        self.matches_tree.column("brand", width=75, minwidth=70, anchor="center", stretch=False)
        self.matches_tree.column("code", width=240, minwidth=170, anchor="w", stretch=True)
        self.matches_tree.column("capacity", width=65, minwidth=60, anchor="center", stretch=False)
        self.matches_tree.column("action", width=105, minwidth=95, anchor="center", stretch=False)

        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.matches_tree.yview)
        self.matches_tree.configure(yscrollcommand=tree_scroll.set)

        self.matches_tree.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)
        tree_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)

        # ดับเบิ้ลคลิก (Double Click) หรือกด Enter เพื่อเพิ่มลงใบเบิก (คลิก 1 ครั้งจะเป็นการเลือกแถวตามปกติ)
        self.matches_tree.bind("<Double-1>", self.on_match_row_double_click)
        self.matches_tree.bind("<ButtonRelease-1>", self.on_match_row_click)
        self.matches_tree.bind("<Return>", lambda e: self.add_selected_match_to_cart(clear_search=True))

        # แถบควบคุมด้านล่างตาราง: จำนวน + หมายเหตุ + ปุ่มเพิ่ม
        action_bar = ctk.CTkFrame(left_panel, fg_color="transparent")
        action_bar.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        action_bar.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(action_bar, text="จำนวน:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.entry_qty = ctk.CTkEntry(action_bar, width=50, height=32, justify="center", font=ctk.CTkFont(size=13, weight="bold"))
        self.entry_qty.insert(0, "1")
        self.entry_qty.grid(row=0, column=1, sticky="w", padx=(0, 2))
        self.entry_qty.bind("<Return>", self.add_from_search)

        ctk.CTkLabel(action_bar, text="ลูก", font=ctk.CTkFont(size=12)).grid(row=0, column=2, sticky="w", padx=(0, 8))

        self.entry_item_remark = ctk.CTkEntry(action_bar, height=32, placeholder_text="หมายเหตุ เช่น เทิร์น, ขั้ว L...")
        self.entry_item_remark.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        self.entry_item_remark.bind("<Return>", self.add_from_search)

        btn_add_match = ctk.CTkButton(
            action_bar, text="➕ เพิ่มลงบิล (Enter)",
            fg_color="#15803d", hover_color="#166534",
            height=32, width=140, font=ctk.CTkFont(weight="bold"),
            command=self.add_from_search
        )
        btn_add_match.grid(row=0, column=4, sticky="e")

        btn_add_custom = ctk.CTkButton(
            action_bar, text="📦 ➕ เพิ่มอะไหล่อื่น",
            fg_color="#ea580c", hover_color="#c2410c",
            height=32, width=130, font=ctk.CTkFont(weight="bold"),
            command=lambda: self.open_custom_item_dialog(),
        )
        btn_add_custom.grid(row=0, column=5, sticky="e", padx=(6, 0))
        self.lbl_quick_toast = ctk.CTkLabel(left_panel, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#15803d")
        self.lbl_quick_toast.grid(row=15, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # แผงขวา: รายการแบตเตอรี่ที่เลือก + สรุป + ปุ่มออก PDF
        right_panel = ctk.CTkFrame(self.panels_container, corner_radius=10)
        right_panel.grid(row=0, column=1, padx=(8, 14), pady=14, sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=14, pady=(12, 0), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header_frame,
            text="📋 รายการแบตเตอรี่จัดขึ้นรถ",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        # ยอดสำหรับตรวจนับ: แบตรวมเป็นลูก + สินค้าอื่นแยกตามชื่อ (ข้อความยาวจะขึ้นบรรทัดใหม่)
        self.lbl_cart_summary = ctk.CTkLabel(
            header_frame,
            text="ยังไม่มีรายการ",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#0e7490",
            justify="left",
            anchor="w",
        )
        self.lbl_cart_summary.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        header_frame.bind(
            "<Configure>",
            lambda e: self.lbl_cart_summary.configure(wraplength=max(e.width - 10, 200)),
        )

        self.cart_frame = ctk.CTkScrollableFrame(right_panel, corner_radius=8)
        self.cart_frame.grid(row=1, column=0, padx=14, pady=6, sticky="nsew")
        self.cart_frame.grid_columnconfigure(1, weight=1)

        checklist_hint = ctk.CTkFrame(right_panel, fg_color=("#e0f2fe", "#164e63"), corner_radius=6)
        checklist_hint.grid(row=2, column=0, padx=14, pady=(4, 6), sticky="ew")
        ctk.CTkLabel(
            checklist_hint, 
            text="⚡ พิมพ์จำนวนแล้วกด Enter ข้ามแถวได้ทันที | กด ▲ / ▼ เพื่อสลับลำดับการจัดขึ้นรถ (หรือกด Ctrl+↑/↓)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("#0369a1", "#bae6fd")
        ).pack(padx=10, pady=6)

        actions_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        actions_frame.grid(row=3, column=0, padx=14, pady=(6, 12), sticky="ew")
        actions_frame.grid_columnconfigure((0, 1), weight=1)

        btn_clear = ctk.CTkButton(
            actions_frame, text="🗑️ ล้างข้อมูล",
            fg_color="#64748b", hover_color="#475569",
            height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.clear_requisition_form
        )
        btn_clear.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.btn_save_pdf = ctk.CTkButton(
            actions_frame, text="🖨️ บันทึกและพิมพ์ PDF (A5 แนวนอน)",
            fg_color="#0e7490", hover_color="#155e75",
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.save_and_print_pdf
        )
        self.btn_save_pdf.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        return view

    def refresh_req_screen(self):
        if not self.editing_req_id:
            self.entry_req_no.delete(0, "end")
            self.entry_req_no.insert(0, generate_next_req_no())

        self.refresh_inventory_cache()

    def refresh_inventory_cache(self):
        """โหลดข้อมูลรุ่นใหม่จากฐานข้อมูล (หลังเพิ่ม/แก้ไข/ลบรุ่น)"""
        self.all_inventory_items = prepare_inventory_items_for_search(inv_service.get_all_items())
        self.refresh_live_matches()

    def refresh_live_matches(self):
        raw_text = self.entry_battery_search.get().strip() if hasattr(self, "entry_battery_search") else ""
        search_kw, qty_spec, remark_spec = parse_battery_quick_entry(raw_text)

        # 1. กรองตาม Brand Chip
        items_pool = self.all_inventory_items
        if hasattr(self, "selected_brand_chip") and self.selected_brand_chip != "ทั้งหมด":
            items_pool = [it for it in items_pool if it.get("brand", "").upper() == self.selected_brand_chip.upper()]

        # 2. ค้นหาตาม search_kw
        if search_kw:
            self.current_scored_matches = find_inventory_matches(items_pool, search_kw)
            self.current_matches = [it for _, it in self.current_scored_matches]
        else:
            self.current_scored_matches = []
            self.current_matches = items_pool
        self.match_selection_moved = False
        self.matches_query = raw_text

        # 3. อัปเดตตาราง
        if hasattr(self, "matches_tree"):
            for row in self.matches_tree.get_children():
                self.matches_tree.delete(row)

            for it in self.current_matches[:100]:
                self.matches_tree.insert(
                    "", "end", iid=str(it["id"]),
                    values=(
                        it.get("brand", "-"),
                        it.get("item_code", "-"),
                        it.get("capacity", "-"),
                        "➕ เพิ่ม"
                    )
                )

            children = self.matches_tree.get_children()
            if children:
                self.matches_tree.selection_set(children[0])
                self.matches_tree.focus(children[0])
                self.lbl_match_count.configure(text=f"พบ {len(self.current_matches)} รุ่น", text_color="#0e7490")
            else:
                self.lbl_match_count.configure(text="ไม่พบ • กด Enter เพิ่มรุ่นใหม่", text_color="#dc2626")

    def on_live_search_key(self, event=None):
        if event and event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self.refresh_live_matches()

    def on_live_search_down(self, event=None):
        children = self.matches_tree.get_children()
        if not children:
            return "break"
        self.match_selection_moved = True
        selected = self.matches_tree.selection()
        if not selected:
            self.matches_tree.selection_set(children[0])
            self.matches_tree.focus(children[0])
            self.matches_tree.see(children[0])
        else:
            curr_idx = children.index(selected[0])
            next_idx = min(curr_idx + 1, len(children) - 1)
            self.matches_tree.selection_set(children[next_idx])
            self.matches_tree.focus(children[next_idx])
            self.matches_tree.see(children[next_idx])
        return "break"

    def on_live_search_up(self, event=None):
        children = self.matches_tree.get_children()
        if not children:
            return "break"
        self.match_selection_moved = True
        selected = self.matches_tree.selection()
        if not selected:
            self.matches_tree.selection_set(children[0])
            self.matches_tree.focus(children[0])
            self.matches_tree.see(children[0])
        else:
            curr_idx = children.index(selected[0])
            prev_idx = max(curr_idx - 1, 0)
            self.matches_tree.selection_set(children[prev_idx])
            self.matches_tree.focus(children[prev_idx])
            self.matches_tree.see(children[prev_idx])
        return "break"

    def on_live_search_enter(self, event=None):
        """Enter ในช่องค้นหา: ดึงจำนวน/หมายเหตุจากรูปแบบคีย์ด่วน (เช่น N100*2*เทิร์น) แล้วเพิ่มตามกฎกลาง"""
        raw_text = self.entry_battery_search.get().strip()
        if not raw_text:
            return "break"
        _, qty_spec, remark_spec = parse_battery_quick_entry(raw_text)
        if qty_spec is not None:
            self.entry_qty.delete(0, "end")
            self.entry_qty.insert(0, str(qty_spec))
        if remark_spec:
            self.entry_item_remark.delete(0, "end")
            self.entry_item_remark.insert(0, remark_spec)
        self.add_from_search()
        return "break"

    def add_from_search(self, event=None):
        """
        กฎกลางสำหรับเพิ่มรุ่นจากตารางค้นหา ใช้ร่วมกันทั้ง Enter ในช่องค้นหา/จำนวน/หมายเหตุ และปุ่ม "เพิ่มลงบิล"
        - ผู้ใช้เลือกแถวเองแล้ว (▲/▼ หรือคลิกแถว) -> เพิ่มแถวนั้น
        - รหัสตรงรุ่นเดียว หรือเจอรุ่นเดียว -> เพิ่มทันที
        - เจอหลายรุ่น -> เปิดหน้าต่างให้เลือก
        - ไม่พบ -> เปิดหน้าต่างเพิ่มแบตเตอรี่รุ่นใหม่
        """
        raw_text = self.entry_battery_search.get().strip()
        if raw_text != self.matches_query:
            # ข้อความเปลี่ยนโดยไม่มีการกดแป้น (เช่น คลิกขวาวาง) -> คำนวณผลค้นหาใหม่ก่อน
            self.refresh_live_matches()
        search_kw = parse_battery_quick_entry(raw_text)[0]

        if self.match_selection_moved and self.matches_tree.selection():
            self.add_selected_match_to_cart(clear_search=True)
            return "break"

        if not search_kw:
            self.show_quick_toast("⚠️ พิมพ์รุ่นที่ต้องการ หรือคลิกเลือกแถวในตารางก่อน", color="#d97706")
            self.entry_battery_search.focus()
            return "break"

        if not self.current_matches:
            qty_text = self.entry_qty.get().strip()
            self.open_new_battery_dialog(
                prefill_text=search_kw,
                prefill_qty=int(qty_text) if qty_text.isdigit() else None,
                prefill_remark=self.entry_item_remark.get().strip(),
            )
            return "break"

        direct = pick_direct_match(self.current_scored_matches, search_kw)
        if direct is not None:
            self.add_item_to_cart(direct, clear_search=True)
        else:
            self.open_match_picker(search_kw)
        return "break"

    def on_match_row_click(self, event):
        if self.matches_tree.identify_row(event.y):
            self.match_selection_moved = True

    def open_match_picker(self, search_kw):
        """เจอหลายรุ่นที่ใกล้เคียงกัน: ให้เลือกรุ่นที่ถูกต้องก่อนเพิ่มลงบิล"""
        matches = self.current_matches[:100]
        dialog = ctk.CTkToplevel(self)
        dialog.title("เลือกรุ่นแบตเตอรี่")
        dialog.geometry("620x380")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"พบ {len(self.current_matches)} รุ่นที่ตรงกับ '{search_kw}' กรุณาเลือกรุ่นที่ถูกต้อง",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=16, pady=(14, 2), anchor="w")
        ctk.CTkLabel(
            dialog,
            text="▲/▼ เลือก • Enter หรือดับเบิลคลิกเพื่อเพิ่ม • Esc ยกเลิก",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(padx=16, pady=(0, 8), anchor="w")

        frame = ctk.CTkFrame(dialog, corner_radius=6)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(frame, columns=("brand", "code", "capacity"), show="headings", selectmode="browse")
        tree.heading("brand", text="ยี่ห้อ")
        tree.heading("code", text="รหัส / รุ่น")
        tree.heading("capacity", text="ความจุ")
        tree.column("brand", width=90, anchor="center", stretch=False)
        tree.column("code", width=380, anchor="w")
        tree.column("capacity", width=80, anchor="center", stretch=False)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)

        by_iid = {}
        for it in matches:
            iid = str(it["id"])
            by_iid[iid] = it
            tree.insert("", "end", iid=iid, values=(it.get("brand", "-"), it.get("item_code", "-"), it.get("capacity", "-")))
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.focus(children[0])

        def choose(event=None):
            sel = tree.selection()
            if not sel:
                return "break"
            item = by_iid[sel[0]]
            dialog.destroy()
            self.add_item_to_cart(item, clear_search=True)
            return "break"

        def cancel(event=None):
            dialog.destroy()
            self.entry_battery_search.focus()
            return "break"

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(btn_box, text="ยกเลิก", fg_color="#64748b", hover_color="#475569", width=90, command=cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_box, text="➕ เพิ่มรุ่นที่เลือก", fg_color="#15803d", hover_color="#166534", width=140, command=choose).pack(side="right")

        tree.bind("<Double-1>", choose)
        dialog.bind("<Return>", choose)
        dialog.bind("<Escape>", cancel)
        dialog.after(100, tree.focus_set)
        self.match_picker_dialog = dialog
        return dialog

    def on_match_row_double_click(self, event):
        region = self.matches_tree.identify_region(event.x, event.y)
        if region not in ("tree", "cell"):
            return
        row_id = self.matches_tree.identify_row(event.y)
        if not row_id:
            return
        self.matches_tree.selection_set(row_id)
        self.matches_tree.focus(row_id)
        self.add_selected_match_to_cart(clear_search=False)

    def clear_live_search(self, event=None):
        self.entry_battery_search.delete(0, "end")
        self.on_select_brand_chip("ทั้งหมด")
        return "break"

    def on_select_brand_chip(self, brand):
        self.selected_brand_chip = brand
        for b, btn in self.brand_chip_buttons.items():
            if b == brand:
                btn.configure(fg_color="#0284c7", text_color="white")
            else:
                btn.configure(fg_color=("#e2e8f0", "#1e293b"), text_color=("#0f172a", "#f8fafc"))
        self.refresh_live_matches()
        self.entry_battery_search.focus()

    def add_selected_match_to_cart(self, clear_search=True):
        selected = self.matches_tree.selection()
        if not selected:
            children = self.matches_tree.get_children()
            if children:
                selected = [children[0]]
            else:
                self.show_quick_toast("❌ ไม่พบรุ่นแบตเตอรี่ที่ตรงกับคำค้นหา", color="#dc2626")
                return False

        try:
            item_id = int(selected[0])
        except (ValueError, TypeError):
            return False

        selected_item = next((it for it in self.all_inventory_items if it["id"] == item_id), None)
        if not selected_item:
            return False
        return self.add_item_to_cart(selected_item, clear_search=clear_search)

    def add_item_to_cart(self, selected_item, clear_search=True, qty=None, remark=None):
        """
        เพิ่มรุ่นจากข้อมูลรุ่นลงใบเบิก
        ถ้าไม่ส่ง qty/remark มา จะใช้ค่าจากช่องจำนวนและหมายเหตุใต้ตารางค้นหา
        """
        if qty is None:
            qty_str = self.entry_qty.get().strip()
            if not qty_str.isdigit() or int(qty_str) <= 0:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุจำนวนลูกให้ถูกต้อง")
                self.entry_qty.focus()
                self.entry_qty.select_range(0, "end")
                return False
            qty = int(qty_str)

        existing_item = next((c for c in self.cart_items if c.get("item_id") == selected_item["id"]), None)

        remark_val = self.entry_item_remark.get().strip() if remark is None else remark
        if existing_item:
            existing_item["quantity"] += qty
            if remark_val:
                existing_item["remark"] = remark_val
        else:
            raw_name = (selected_item.get("item_name") or "").strip()
            code = (selected_item.get("item_code") or "").strip()
            brand = (selected_item.get("brand") or "").strip()
            category = selected_item.get("category") or BATTERY

            # ตัดความซ้ำซ้อน ให้เหลือแค่: แบตเตอรี่ [ยี่ห้อ] [รุ่น]
            if raw_name:
                display_name = raw_name
                if category == BATTERY and not display_name.startswith(BATTERY):
                    display_name = f"{BATTERY} {display_name}"
            else:
                display_name = f"{BATTERY} {brand} {code}".strip()
            display_name = re.sub(r"\s+", " ", display_name).strip()

            self.cart_items.append({
                "item_id": selected_item["id"],
                "brand": selected_item["brand"],
                "item_code": selected_item["item_code"],
                "item_name": display_name,
                "capacity": selected_item.get("capacity") or "-",
                "unit": selected_item.get("unit") or "ลูก",
                "quantity": qty,
                "remark": remark_val,
                "category": category,
            })

        self.entry_qty.delete(0, "end")
        self.entry_qty.insert(0, "1")
        self.entry_item_remark.delete(0, "end")

        self.render_cart_items()

        # เลื่อนหน้าจอรายการจัดขึ้นรถ (Auto-scroll) ไปยังรายการล่าสุดอัตโนมัติ
        try:
            self.cart_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

        msg = f"⚡ เพิ่ม [{selected_item['brand']}] {selected_item['item_code']} x {qty} ลูก เข้าใบเบิกแล้ว!"
        if remark_val:
            msg += f" ({remark_val})"
        self.show_quick_toast(msg, color="#15803d")

        if clear_search:
            self.entry_battery_search.delete(0, "end")
            self.refresh_live_matches()
            self.entry_battery_search.focus()
        return True

    def show_quick_toast(self, msg, color="#15803d"):
        if hasattr(self, "lbl_quick_toast"):
            self.lbl_quick_toast.configure(text=msg, text_color=color)
            self.after(3500, lambda: self.lbl_quick_toast.configure(text=""))

    def focus_quick_search(self):
        self.entry_battery_search.focus()
        self.entry_battery_search.select_range(0, "end")

    def render_cart_items(self):
        for widget in self.cart_frame.winfo_children():
            widget.destroy()

        # Rebuild the keyboard-navigation lists together with the row widgets.
        # Keeping entries from an earlier render makes Enter target a widget
        # that has already been destroyed.
        self.cart_qty_entries = []
        self.cart_rem_entries = []
        self.cart_name_entries = []
        if not self.cart_items:
            lbl_empty = ctk.CTkLabel(
                self.cart_frame, 
                text="ยังไม่มีรายการแบตเตอรี่\nกรุณาค้นหารุ่นแบตจากแผงด้านซ้ายแล้วกด Enter หรือปุ่ม 'เพิ่มลงบิล'", 
                text_color="gray",
                pady=40
            )
            lbl_empty.pack()
            self.update_cart_summary()
            return

        for idx, item in enumerate(self.cart_items):
            row_frame = ctk.CTkFrame(self.cart_frame, corner_radius=8)
            row_frame.pack(fill="x", padx=6, pady=6)

            # ==========================================
            # แถวที่ 1 (แถวบน): ป้ายลำดับ/ยี่ห้อ + กล่องข้อความพิมพ์ชื่อรุ่น/คำได้อิสระ (Inline Editable)
            # ==========================================
            top_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            top_frame.pack(fill="x", padx=12, pady=(8, 4))

            badge = ctk.CTkLabel(
                top_frame, 
                text=f"{idx+1}. [{item['brand'] if is_battery(item) else item_category(item)}]", 
                font=ctk.CTkFont(weight="bold", size=15),
                anchor="w"
            )
            badge.pack(side="left", padx=(0, 6))

            entry_inline_name = ctk.CTkEntry(
                top_frame, 
                height=32, 
                font=ctk.CTkFont(size=14, weight="bold")
            )
            name_val = str(item.get("item_name") or item.get("item_code", ""))
            entry_inline_name.insert(0, name_val)
            entry_inline_name.pack(side="left", fill="x", expand=True)
            self.cart_name_entries.append(entry_inline_name)

            entry_inline_name.bind(
                "<KeyRelease>", 
                lambda e, i=idx, ent=entry_inline_name: self.on_cart_name_change(i, ent)
            )
            entry_inline_name.bind("<Return>", lambda e, i=idx: self.jump_from_name_to_rem(i))
            entry_inline_name.bind("<Down>", lambda e, i=idx: self.jump_from_name_to_rem(i))

            # ==========================================
            # แถวที่ 2 (แถวล่าง): ช่องพิมพ์หมายเหตุ (ซ้าย) + กลุ่มปุ่มควบคุมทั้งหมด (ขวา)
            # ==========================================
            bot_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            bot_frame.pack(fill="x", padx=12, pady=(2, 8))

            controls_frame = ctk.CTkFrame(bot_frame, fg_color="transparent")
            controls_frame.pack(side="right")

            btn_del = ctk.CTkButton(
                controls_frame, text="❌", width=34, height=30,
                fg_color="#ef4444", hover_color="#dc2626",
                font=ctk.CTkFont(size=13),
                command=lambda i=idx: self.remove_cart_item(i)
            )
            btn_del.pack(side="right", padx=(6, 0))

            qty_control = ctk.CTkFrame(controls_frame, fg_color="transparent")
            qty_control.pack(side="right", padx=4)

            btn_minus = ctk.CTkButton(
                qty_control, text="➖", width=28, height=30,
                fg_color=("#cbd5e1", "#334155"), text_color=("black", "white"),
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda i=idx: self.adjust_cart_qty(i, -1)
            )
            btn_minus.pack(side="left", padx=1)

            entry_inline_qty = ctk.CTkEntry(
                qty_control, width=48, height=30,
                justify="center", font=ctk.CTkFont(size=15, weight="bold")
            )
            entry_inline_qty.insert(0, str(item["quantity"]))
            entry_inline_qty.pack(side="left", padx=1)
            self.cart_qty_entries.append(entry_inline_qty)

            entry_inline_qty.bind("<KeyRelease>", lambda e, i=idx, ent=entry_inline_qty: self.on_cart_qty_change(i, ent))
            entry_inline_qty.bind("<FocusOut>", lambda e, i=idx, ent=entry_inline_qty: self.on_cart_qty_validate(i, ent))
            entry_inline_qty.bind("<Return>", lambda e, i=idx, ent=entry_inline_qty: self.jump_to_next_cart_qty(i, ent))
            entry_inline_qty.bind("<Down>", lambda e, i=idx, ent=entry_inline_qty: self.jump_to_next_cart_qty(i, ent))
            entry_inline_qty.bind("<Up>", lambda e, i=idx, ent=entry_inline_qty: self.jump_to_prev_cart_qty(i, ent))
            entry_inline_qty.bind("<Control-Up>", lambda e, i=idx: self.move_cart_item(i, -1))
            entry_inline_qty.bind("<Control-Down>", lambda e, i=idx: self.move_cart_item(i, 1))
            entry_inline_qty.bind("<Alt-Up>", lambda e, i=idx: self.move_cart_item(i, -1))
            entry_inline_qty.bind("<Alt-Down>", lambda e, i=idx: self.move_cart_item(i, 1))

            btn_plus = ctk.CTkButton(
                qty_control, text="➕", width=28, height=30,
                fg_color=("#cbd5e1", "#334155"), text_color=("black", "white"),
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda i=idx: self.adjust_cart_qty(i, +1)
            )
            btn_plus.pack(side="left", padx=1)

            unit_text = str(item.get("unit") or "ลูก")
            ctk.CTkLabel(qty_control, text=unit_text, font=ctk.CTkFont(size=13, weight="bold"), width=28).pack(side="left", padx=2)

            btn_edit_row = ctk.CTkButton(
                controls_frame, text="✏️ แก้ไข", width=62, height=30,
                command=lambda i=idx: self.open_edit_cart_item_dialog(i)
            )
            btn_edit_row.pack(side="right", padx=4)

            reorder_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
            reorder_frame.pack(side="right", padx=(0, 4))

            btn_up = ctk.CTkButton(
                reorder_frame, text="▲", width=28, height=30,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#e2e8f0", "#334155") if idx > 0 else ("#f1f5f9", "#1e293b"),
                text_color=("#0f172a", "#f8fafc") if idx > 0 else ("#94a3b8", "#64748b"),
                hover_color="#cbd5e1" if idx > 0 else ("#f1f5f9", "#1e293b"),
                state="normal" if idx > 0 else "disabled",
                command=lambda i=idx: self.move_cart_item(i, -1)
            )
            btn_up.pack(side="left", padx=1)

            btn_down = ctk.CTkButton(
                reorder_frame, text="▼", width=28, height=30,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#e2e8f0", "#334155") if idx < len(self.cart_items) - 1 else ("#f1f5f9", "#1e293b"),
                text_color=("#0f172a", "#f8fafc") if idx < len(self.cart_items) - 1 else ("#94a3b8", "#64748b"),
                hover_color="#cbd5e1" if idx < len(self.cart_items) - 1 else ("#f1f5f9", "#1e293b"),
                state="normal" if idx < len(self.cart_items) - 1 else "disabled",
                command=lambda i=idx: self.move_cart_item(i, 1)
            )
            btn_down.pack(side="left", padx=1)

            # ฝั่งซ้าย: ช่องพิมพ์หมายเหตุ/รายละเอียดเพิ่มเติม ขยายเต็มพื้นที่ที่เหลือ
            rem_frame = ctk.CTkFrame(bot_frame, fg_color="transparent")
            rem_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))

            ctk.CTkLabel(rem_frame, text="หมายเหตุ:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").pack(
                side="left", padx=(0, 6)
            )
            entry_inline_rem = ctk.CTkEntry(
                rem_frame, height=32,
                placeholder_text="เทิร์นลูกเก่า, ขั้ว L, ส่งด่วน...",
                font=ctk.CTkFont(size=13)
            )
            if item.get("remark"):
                entry_inline_rem.insert(0, str(item["remark"]))
            entry_inline_rem.pack(side="left", fill="x", expand=True)
            self.cart_rem_entries.append(entry_inline_rem)

            entry_inline_rem.bind(
                "<KeyRelease>", 
                lambda e, i=idx, ent=entry_inline_rem: self.on_cart_remark_change(i, ent)
            )
            entry_inline_rem.bind("<Return>", lambda e, i=idx: self.jump_to_next_cart_rem(i))
            entry_inline_rem.bind("<Down>", lambda e, i=idx: self.jump_to_next_cart_rem(i))
            entry_inline_rem.bind("<Up>", lambda e, i=idx: self.jump_to_prev_cart_rem(i))


        self.update_cart_summary()

    def move_cart_item(self, index, direction):
        new_index = index + direction
        if 0 <= new_index < len(self.cart_items):
            self.cart_items[index], self.cart_items[new_index] = self.cart_items[new_index], self.cart_items[index]
            self.render_cart_items()
            if 0 <= new_index < len(self.cart_qty_entries):
                self.cart_qty_entries[new_index].focus()
                self.cart_qty_entries[new_index].select_range(0, "end")

    def focus_first_cart_qty(self):
        if self.cart_qty_entries:
            self.cart_qty_entries[0].focus()
            self.cart_qty_entries[0].select_range(0, "end")

    def jump_to_next_cart_qty(self, current_idx, current_entry):
        self.on_cart_qty_validate(current_idx, current_entry)
        next_idx = current_idx + 1
        if next_idx < len(self.cart_qty_entries):
            next_entry = self.cart_qty_entries[next_idx]
            next_entry.focus_set()
            next_entry.select_range(0, "end")
            try:
                self.cart_frame._parent_canvas.yview_moveto(next_idx / max(len(self.cart_qty_entries), 1))
            except Exception:
                pass
        else:
            self.show_quick_toast("✓ ใส่จำนวนครบทุกรายการแล้ว (กด Ctrl+S เพื่อบันทึก)")
            self.btn_save_pdf.focus_set()
        return "break"

    def jump_to_prev_cart_qty(self, current_idx, current_entry):
        self.on_cart_qty_validate(current_idx, current_entry)
        prev_idx = current_idx - 1
        if prev_idx >= 0:
            prev_entry = self.cart_qty_entries[prev_idx]
            prev_entry.focus_set()
            prev_entry.select_range(0, "end")
            try:
                self.cart_frame._parent_canvas.yview_moveto(prev_idx / max(len(self.cart_qty_entries), 1))
            except Exception:
                pass
        return "break"

    def jump_to_next_cart_rem(self, current_idx):
        next_idx = current_idx + 1
        if next_idx < len(self.cart_rem_entries):
            self.cart_rem_entries[next_idx].focus()
            self.cart_rem_entries[next_idx].select_range(0, "end")
        else:
            self.btn_save_pdf.focus()

    def jump_to_prev_cart_rem(self, current_idx):
        prev_idx = current_idx - 1
        if prev_idx >= 0:
            self.cart_rem_entries[prev_idx].focus()
            self.cart_rem_entries[prev_idx].select_range(0, "end")

    def on_cart_remark_change(self, index, entry_widget):
        if 0 <= index < len(self.cart_items):
            self.cart_items[index]["remark"] = entry_widget.get().strip()

    def on_cart_name_change(self, index, entry_widget):
        if 0 <= index < len(self.cart_items):
            self.cart_items[index]["item_name"] = entry_widget.get().strip()

    def jump_from_name_to_rem(self, current_idx):
        if current_idx < len(self.cart_rem_entries):
            self.cart_rem_entries[current_idx].focus()
            self.cart_rem_entries[current_idx].select_range(0, "end")
        return "break"

    def _prefill_from_search(self, prefill_text, prefill_qty, prefill_remark):
        """ใช้ข้อความในช่องค้นหา (เช่น "FB N999*2*เทิร์น") เป็นค่าเริ่มต้นของหน้าต่างเพิ่มสินค้า"""
        if not prefill_text and hasattr(self, "entry_battery_search"):
            raw = self.entry_battery_search.get().strip()
            if raw:
                kw, q, rem = parse_battery_quick_entry(raw)
                prefill_text = kw
                if q is not None and prefill_qty is None:
                    prefill_qty = q
                if rem and not prefill_remark:
                    prefill_remark = rem
        return prefill_text or "", prefill_qty, prefill_remark or ""

    def _known_brands(self):
        return sorted({(it.get("brand") or "").strip().upper() for it in self.all_inventory_items if it.get("brand")})

    def _split_brand_prefix(self, text):
        """แยกยี่ห้อที่พิมพ์มาข้างหน้า เช่น "FB N999" -> ("FB", "N999")"""
        parts = (text or "").strip().split(" ", 1)
        if len(parts) == 2:
            word = parts[0].upper()
            if word in self._known_brands() or detect_brand(word) == word:
                return word, parts[1].strip()
        return "", (text or "").strip()

    def _center_dialog(self, dialog, width, height):
        dialog.geometry(f"{width}x{height}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - width) // 2
        y = self.winfo_y() + (self.winfo_height() - height) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def open_new_battery_dialog(self, prefill_text="", prefill_qty=None, prefill_remark="", for_requisition=True):
        """
        เพิ่มแบตเตอรี่รุ่นใหม่เข้าข้อมูลรุ่น ใช้ทั้งในหน้าออกใบเบิก (เพิ่มลงบิลได้ทันที)
        และหน้าข้อมูลรุ่นแบตเตอรี่ (for_requisition=False)
        """
        if for_requisition:
            prefill_text, prefill_qty, prefill_remark = self._prefill_from_search(prefill_text, prefill_qty, prefill_remark)
        prefill_brand, prefill_model = self._split_brand_prefix(prefill_text)

        dialog = ctk.CTkToplevel(self)
        dialog.title("🔋 เพิ่มแบตเตอรี่รุ่นใหม่")
        self._center_dialog(dialog, 540, 560 if for_requisition else 400)

        ctk.CTkLabel(dialog, text="🔋 เพิ่มแบตเตอรี่รุ่นใหม่", font=ctk.CTkFont(size=16, weight="bold")).pack(
            padx=20, pady=(16, 2), anchor="w"
        )
        ctk.CTkLabel(
            dialog,
            text="รุ่นจะถูกบันทึกในข้อมูลรุ่นแบตเตอรี่ ครั้งหน้าค้นหาเจอทันที",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(padx=20, pady=(0, 10), anchor="w")

        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=4)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="ยี่ห้อ:*", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=6)
        combo_brand = ctk.CTkComboBox(form, values=self._known_brands() or [""])
        combo_brand.set(prefill_brand)
        combo_brand.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="รุ่น:*", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, sticky="w", pady=6)
        entry_model = ctk.CTkEntry(form, placeholder_text="เช่น 55D23L, N100, DIN75")
        if prefill_model:
            entry_model.insert(0, prefill_model)
        entry_model.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="ความจุ:").grid(row=2, column=0, sticky="w", pady=6)
        entry_cap = ctk.CTkEntry(form, placeholder_text="เช่น 45 Ah (ไม่ระบุก็ได้)")
        entry_cap.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="ประเภท:").grid(row=3, column=0, sticky="w", pady=6)
        combo_type = ctk.CTkComboBox(form, values=BATTERY_TYPES, state="readonly")
        combo_type.set(BATTERY_TYPES[0])
        combo_type.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=6)

        lbl_preview = ctk.CTkLabel(form, text="", text_color="#0e7490", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_preview.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 6))

        def compose_code():
            brand = combo_brand.get().strip().upper()
            model = " ".join(entry_model.get().split())
            if not brand or not model:
                return brand, model, ""
            code = model if model.upper().startswith(brand) else f"{brand} {model}"
            return brand, model, code

        def update_preview(*_):
            _, _, code = compose_code()
            lbl_preview.configure(text=f"ชื่อที่จะบันทึก: {BATTERY} {code}" if code else "")

        entry_model.bind("<KeyRelease>", update_preview)
        combo_brand.bind("<KeyRelease>", update_preview)
        combo_brand.configure(command=update_preview)
        update_preview()

        var_add_to_bill = tk.BooleanVar(value=for_requisition)
        entry_qty = entry_rem = None
        if for_requisition:
            chk = ctk.CTkCheckBox(form, text="เพิ่มลงใบเบิกนี้ด้วย", variable=var_add_to_bill)
            chk.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 4))

            ctk.CTkLabel(form, text="จำนวน (ลูก):").grid(row=6, column=0, sticky="w", pady=6)
            entry_qty = ctk.CTkEntry(form, width=80, justify="center", font=ctk.CTkFont(size=14, weight="bold"))
            entry_qty.insert(0, str(prefill_qty if prefill_qty is not None else 1))
            entry_qty.grid(row=6, column=1, sticky="w", padx=(10, 0), pady=6)

            ctk.CTkLabel(form, text="หมายเหตุ:").grid(row=7, column=0, sticky="w", pady=6)
            entry_rem = ctk.CTkEntry(form, placeholder_text="เช่น เทิร์นลูกเก่า, ขั้ว L...")
            if prefill_remark:
                entry_rem.insert(0, prefill_remark)
            entry_rem.grid(row=7, column=1, sticky="ew", padx=(10, 0), pady=6)

            def toggle_bill_fields():
                state = "normal" if var_add_to_bill.get() else "disabled"
                entry_qty.configure(state=state)
                entry_rem.configure(state=state)

            chk.configure(command=toggle_bill_fields)

        def save():
            brand, model, code = compose_code()
            if not brand:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุยี่ห้อแบตเตอรี่", parent=dialog)
                combo_brand.focus()
                return
            if not model:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุรุ่นแบตเตอรี่", parent=dialog)
                entry_model.focus()
                return

            add_to_bill = for_requisition and var_add_to_bill.get()
            qty = None
            remark = ""
            if add_to_bill:
                qty_str = entry_qty.get().strip()
                if not qty_str.isdigit() or int(qty_str) <= 0:
                    messagebox.showwarning("แจ้งเตือน", "กรุณาระบุจำนวนลูกให้ถูกต้อง", parent=dialog)
                    entry_qty.focus()
                    return
                qty = int(qty_str)
                remark = entry_rem.get().strip()

            existing = inv_service.get_item_by_code(code)
            if existing and not for_requisition:
                messagebox.showwarning("แจ้งเตือน", f"รหัสรุ่น '{code}' มีอยู่ในระบบแล้ว", parent=dialog)
                return

            if existing:
                item = existing
            else:
                battery_type = combo_type.get()
                if battery_type == BATTERY_TYPES[0]:
                    battery_type = "-"
                try:
                    inv_service.add_item(
                        brand, code, f"{BATTERY} {code}", entry_cap.get().strip() or "-",
                        battery_type, "ลูก", 9999, 0, category=BATTERY,
                    )
                except Exception as ex:
                    messagebox.showerror("ผิดพลาด", f"บันทึกรุ่นใหม่ไม่สำเร็จ: {ex}", parent=dialog)
                    return
                item = inv_service.get_item_by_code(code)

            dialog.destroy()
            self.refresh_inventory_cache()
            if hasattr(self, "stock_tree"):
                self.refresh_stock_table()

            if add_to_bill:
                self.add_item_to_cart(item, clear_search=True, qty=qty, remark=remark)
                if existing:
                    self.show_quick_toast(f"ℹ️ มีรุ่น {code} อยู่แล้ว เพิ่มรุ่นเดิมลงใบเบิก x {qty} ลูก", color="#0e7490")
            elif existing:
                messagebox.showinfo("แจ้งเตือน", f"มีรุ่น '{code}' อยู่ในระบบแล้ว ไม่ได้บันทึกซ้ำ")
            else:
                self.show_quick_toast(f"✅ บันทึกรุ่นใหม่ {code} เรียบร้อย")
                if for_requisition and hasattr(self, "entry_battery_search"):
                    self.entry_battery_search.delete(0, "end")
                    self.refresh_live_matches()

        def switch_to_part():
            text = " ".join(x for x in (combo_brand.get().strip(), entry_model.get().strip()) if x)
            qty_text = entry_qty.get().strip() if entry_qty else ""
            remark = entry_rem.get().strip() if entry_rem else ""
            dialog.destroy()
            self.open_custom_item_dialog(
                prefill_name=text,
                prefill_qty=int(qty_text) if qty_text.isdigit() else None,
                prefill_remark=remark,
            )

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(fill="x", side="bottom", padx=20, pady=(8, 16))
        ctk.CTkButton(btn_box, text="ยกเลิก", fg_color="#64748b", hover_color="#475569", width=90,
                      command=dialog.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_box, text="💾 บันทึกรุ่นใหม่", fg_color="#15803d", hover_color="#166534", width=140,
                      font=ctk.CTkFont(weight="bold"), command=save).pack(side="right")
        if for_requisition:
            ctk.CTkButton(btn_box, text="ไม่ใช่แบต → เพิ่มเป็นอะไหล่/สินค้าอื่น", fg_color="transparent",
                          border_width=1, border_color="#ea580c", text_color=("#c2410c", "#fdba74"),
                          hover_color=("#ffedd5", "#431407"), command=switch_to_part).pack(side="left")

        dialog.bind("<Return>", lambda e: save())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.after(100, lambda: (entry_model if prefill_brand or not prefill_model else combo_brand).focus())

        self.new_battery_dialog = dialog
        dialog.form_widgets = {
            "brand": combo_brand, "model": entry_model, "capacity": entry_cap, "type": combo_type,
            "add_to_bill": var_add_to_bill, "qty": entry_qty, "remark": entry_rem,
            "save": save, "switch_to_part": switch_to_part, "preview": lbl_preview,
        }
        return dialog

    def open_custom_item_dialog(self, prefill_name="", prefill_qty=None, prefill_remark=""):
        """เพิ่มอะไหล่ / สินค้าอื่นที่ไม่ใช่แบตเตอรี่ลงใบเบิก (ไม่บันทึกเข้าข้อมูลรุ่น)"""
        prefill_name, prefill_qty, prefill_remark = self._prefill_from_search(prefill_name, prefill_qty, prefill_remark)

        dialog = ctk.CTkToplevel(self)
        dialog.title("📦 เพิ่มอะไหล่ / สินค้าทั่วไป (ไม่ใช่แบตเตอรี่)")
        self._center_dialog(dialog, 520, 440)

        ctk.CTkLabel(
            dialog,
            text="📦 เพิ่มอะไหล่ / สินค้าอื่นๆ ลงในใบเบิก",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(padx=20, pady=(16, 4), anchor="w")

        ctk.CTkLabel(
            dialog,
            text="เช่น ไดชาร์จ, ไดสตาร์ท, ขั้วแบต, น้ำกลั่น • ถ้าเป็นแบตเตอรี่ให้ใช้ปุ่ม \"➕ เพิ่มแบตรุ่นใหม่\"",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(padx=20, pady=(0, 12), anchor="w")

        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=4)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="หมวดสินค้า:*", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=6)
        combo_category = ctk.CTkComboBox(form, values=OTHER_CATEGORIES, state="readonly")
        combo_category.set(OTHER_CATEGORIES[0])
        combo_category.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="ชื่อสินค้า/อะไหล่:*", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, sticky="w", pady=6)
        entry_custom_name = ctk.CTkEntry(form, placeholder_text="เช่น ไดชาร์จ โตโยต้า วีโก้ 80A, ลูกปืนล้อหน้า NSK...")
        if prefill_name:
            entry_custom_name.insert(0, prefill_name)
        entry_custom_name.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="จำนวน:*", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w", pady=6)
        entry_custom_qty = ctk.CTkEntry(form, width=80, justify="center", font=ctk.CTkFont(size=14, weight="bold"))
        entry_custom_qty.insert(0, str(prefill_qty if prefill_qty is not None else 1))
        entry_custom_qty.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="หน่วยนับ:*", font=ctk.CTkFont(weight="bold")).grid(row=3, column=0, sticky="w", pady=6)
        combo_custom_unit = ctk.CTkComboBox(form, values=[u for u in UNIT_CHOICES if u != "ลูก"])
        combo_custom_unit.set("ตัว")
        combo_custom_unit.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="หมายเหตุเสริม:").grid(row=4, column=0, sticky="w", pady=6)
        entry_custom_rem = ctk.CTkEntry(form, placeholder_text="เช่น ของแท้ศูนย์, เบิกด่วน...")
        if prefill_remark:
            entry_custom_rem.insert(0, prefill_remark)
        entry_custom_rem.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=6)

        def add_and_close():
            name = entry_custom_name.get().strip()
            if not name:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุชื่อสินค้า/อะไหล่", parent=dialog)
                entry_custom_name.focus()
                return

            qty_str = entry_custom_qty.get().strip()
            if not qty_str.isdigit() or int(qty_str) <= 0:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุจำนวนที่ถูกต้อง", parent=dialog)
                entry_custom_qty.focus()
                return
            qty = int(qty_str)

            category = combo_category.get().strip() or OTHER_CATEGORIES[0]
            unit = combo_custom_unit.get().strip() or "ตัว"
            rem = entry_custom_rem.get().strip()

            self.cart_items.append({
                "item_id": None,
                "brand": category,
                "item_code": name,
                "item_name": name,
                "capacity": "-",
                "unit": unit,
                "quantity": qty,
                "remark": rem,
                "category": category,
            })

            self.render_cart_items()
            try:
                self.cart_frame._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass

            self.show_quick_toast(f"📦 เพิ่ม [{category}] {name} x {qty} {unit} เข้าใบเบิกแล้ว!")
            if hasattr(self, "entry_battery_search"):
                self.entry_battery_search.delete(0, "end")
                self.refresh_live_matches()

            dialog.destroy()

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(16, 16))

        ctk.CTkButton(btn_box, text="ยกเลิก", fg_color="#64748b", hover_color="#475569", width=90,
                      command=dialog.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_box, text="➕ เพิ่มลงในใบเบิก",
            fg_color="#ea580c", hover_color="#c2410c",
            width=140, font=ctk.CTkFont(weight="bold"),
            command=add_and_close
        ).pack(side="right")

        dialog.bind("<Return>", lambda e: add_and_close())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        entry_custom_name.focus()

        self.custom_item_dialog = dialog
        dialog.form_widgets = {
            "category": combo_category, "name": entry_custom_name, "qty": entry_custom_qty,
            "unit": combo_custom_unit, "remark": entry_custom_rem, "submit": add_and_close,
        }
        return dialog

    def open_edit_cart_item_dialog(self, index):
        if not (0 <= index < len(self.cart_items)):
            return
        item = self.cart_items[index]

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"✏️ แก้ไขรายละเอียดสินค้า - {item['item_code']}")
        dialog.geometry("520x420")
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 520) // 2
        y = self.winfo_y() + (self.winfo_height() - 420) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text=f"✏️ แก้ไขข้อมูล: [{item['brand']}] {item['item_code']}", font=ctk.CTkFont(size=15, weight="bold")).pack(padx=20, pady=(16, 12), anchor="w")

        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=4)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="รหัสรุ่น (Code):").grid(row=0, column=0, sticky="w", pady=6)
        entry_code = ctk.CTkEntry(form)
        entry_code.insert(0, item.get("item_code", ""))
        entry_code.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="ชื่อสินค้า / รายละเอียด:").grid(row=1, column=0, sticky="w", pady=6)
        entry_name = ctk.CTkEntry(form)
        entry_name.insert(0, item.get("item_name", ""))
        entry_name.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="ความจุ (Capacity):").grid(row=2, column=0, sticky="w", pady=6)
        entry_cap = ctk.CTkEntry(form)
        entry_cap.insert(0, item.get("capacity") or "")
        entry_cap.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="จำนวน:").grid(row=3, column=0, sticky="w", pady=6)
        entry_qty = ctk.CTkEntry(form)
        entry_qty.insert(0, str(item.get("quantity", 1)))
        entry_qty.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="หน่วยนับ:").grid(row=4, column=0, sticky="w", pady=6)
        combo_unit = ctk.CTkComboBox(form, values=UNIT_CHOICES)
        combo_unit.set(item.get("unit", "ลูก"))
        combo_unit.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text="หมายเหตุเสริม:").grid(row=5, column=0, sticky="w", pady=6)
        entry_remark = ctk.CTkEntry(form, placeholder_text="เช่น เทิร์นลูกเก่า, ขั้ว L, ของแถม...")
        entry_remark.insert(0, item.get("remark") or "")
        entry_remark.grid(row=5, column=1, sticky="ew", padx=(10, 0), pady=6)

        def save_changes():
            qty_val = entry_qty.get().strip()
            if not qty_val.isdigit() or int(qty_val) <= 0:
                messagebox.showwarning("แจ้งเตือน", "กรุณาระบุจำนวนให้ถูกต้อง", parent=dialog)
                return
            item["item_code"] = entry_code.get().strip() or item["item_code"]
            item["item_name"] = entry_name.get().strip() or item["item_name"]
            item["capacity"] = entry_cap.get().strip() or "-"
            item["quantity"] = int(qty_val)
            item["unit"] = combo_unit.get().strip() or "ลูก"
            item["remark"] = entry_remark.get().strip()

            self.render_cart_items()
            dialog.destroy()

        def delete_item():
            confirm = messagebox.askyesno("ยืนยันการลบ", f"ต้องการลบรายการ '{item['brand']} {item['item_code']}' ออกจากใบเบิกหรือไม่?", parent=dialog)
            if confirm:
                dialog.destroy()
                self.remove_cart_item(index)

        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(20, 16))

        btn_del_dlg = ctk.CTkButton(btn_box, text="🗑️ ลบรายการนี้", fg_color="#ef4444", hover_color="#dc2626", width=115, command=delete_item)
        btn_del_dlg.pack(side="left")

        btn_cancel = ctk.CTkButton(btn_box, text="ยกเลิก", fg_color="#64748b", hover_color="#475569", width=100, command=dialog.destroy)
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_save = ctk.CTkButton(btn_box, text="💾 บันทึกการแก้ไข", fg_color="#15803d", hover_color="#166534", width=130, command=save_changes)
        btn_save.pack(side="right", padx=8)

    def adjust_cart_qty(self, index, delta):
        item = self.cart_items[index]
        new_qty = item["quantity"] + delta
        if new_qty <= 0:
            confirm = messagebox.askyesno("ยืนยัน", f"ต้องการลบรายการ '{item['brand']} {item['item_code']}' ออกจากใบเบิกหรือไม่?")
            if confirm:
                self.remove_cart_item(index)
            return

        item["quantity"] = new_qty
        self.render_cart_items()

    def on_cart_qty_change(self, index, entry_widget):
        if not (0 <= index < len(self.cart_items)):
            return
        val = entry_widget.get().strip()
        if not val:
            return
        if val.isdigit():
            new_qty = int(val)
            if new_qty > 0:
                self.cart_items[index]["quantity"] = new_qty
                self.update_cart_summary()

    def on_cart_qty_validate(self, index, entry_widget):
        if not (0 <= index < len(self.cart_items)):
            return
        val = entry_widget.get().strip()
        if not val or not val.isdigit() or int(val) <= 0:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(self.cart_items[index]["quantity"]))
        self.update_cart_summary()

    def update_cart_summary(self):
        if not self.cart_items:
            self.lbl_cart_summary.configure(text="ยังไม่มีรายการ")
            return
        breakdown = format_breakdown(count_breakdown(self.cart_items))
        self.lbl_cart_summary.configure(text=f"ตรวจนับ ({len(self.cart_items)} รายการ): {breakdown}")

    def remove_cart_item(self, index):
        if 0 <= index < len(self.cart_items):
            self.cart_items.pop(index)
            self.render_cart_items()

    def clear_requisition_form(self):
        self.exit_edit_mode()

    def exit_edit_mode(self):
        self.editing_req_id = None
        if hasattr(self, "edit_banner_frame"):
            self.edit_banner_frame.grid_forget()
        if hasattr(self, "btn_save_pdf"):
            self.btn_save_pdf.configure(text="🖨️ บันทึกและพิมพ์ PDF (A5 แนวนอน)", fg_color="#0e7490", hover_color="#155e75")
        self.cart_items = []
        self.render_cart_items()
        self.entry_vehicle.delete(0, "end")
        self.entry_driver.delete(0, "end")
        self.entry_customer.delete(0, "end")
        self.entry_ref_bill.delete(0, "end")
        self.entry_purpose.delete(0, "end")
        if hasattr(self, "combo_route"):
            self.combo_route.set("")
        self.refresh_req_screen()

    def save_and_print_pdf(self):
        vehicle = self.entry_vehicle.get().strip() or "-"
        driver = self.entry_driver.get().strip() or "-"
        customer = self.entry_customer.get().strip()
        route = self.combo_route.get().strip()
        ref_bill = self.entry_ref_bill.get().strip()
        purpose = self.entry_purpose.get().strip()
        req_no = self.entry_req_no.get().strip()

        if not customer:
            messagebox.showwarning("แจ้งเตือน", "กรุณาระบุชื่อลูกค้า / ร้านค้าปลายทาง")
            self.entry_customer.focus()
            return

        try:
            req_date = normalize_req_date(self.entry_req_date.get())
        except ValueError as e:
            messagebox.showwarning("วันที่ไม่ถูกต้อง", f"{e}\nรองรับ เช่น 3/9/2026, 03/09/2026 หรือปี พ.ศ. 3/9/2569")
            self.entry_req_date.focus()
            return
        self.entry_req_date.delete(0, "end")
        self.entry_req_date.insert(0, req_date)

        if not self.cart_items:
            messagebox.showwarning("แจ้งเตือน", "กรุณาเพิ่มรายการแบตเตอรี่อย่างน้อย 1 รายการก่อนบันทึก")
            return

        if len(self.cart_items) > 15:
            messagebox.showwarning(
                "รายการเกินหนึ่งบิล",
                f"ใบเบิก A5 รองรับได้สูงสุด 15 รายการต่อบิล\n"
                f"ขณะนี้มี {len(self.cart_items)} รายการ กรุณาแยกเป็นใบเบิกถัดไปก่อนบันทึก",
            )
            return

        # ขั้นที่ 1: บันทึกลงฐานข้อมูล
        try:
            if self.editing_req_id:
                req_id, final_req_no = inv_service.update_requisition(
                    req_id=self.editing_req_id,
                    driver_name=driver,
                    vehicle_plate=vehicle,
                    customer_name=customer,
                    route_zone=route,
                    ref_bill_no=ref_bill,
                    purpose=purpose,
                    req_items=self.cart_items,
                    req_date=req_date
                )
                success_msg = f"แก้ไขใบเบิก {final_req_no} เรียบร้อยแล้ว!"
            else:
                req_id, final_req_no = inv_service.create_requisition(
                    driver_name=driver,
                    vehicle_plate=vehicle,
                    customer_name=customer,
                    route_zone=route,
                    ref_bill_no=ref_bill,
                    purpose=purpose,
                    req_items=self.cart_items,
                    custom_req_no=req_no,
                    req_date=req_date
                )
                success_msg = f"สร้างใบเบิกเลขที่ {final_req_no} เรียบร้อยแล้ว!"
        except Exception as e:
            messagebox.showerror("บันทึกไม่สำเร็จ", str(e))
            return

        # ขั้นที่ 2: สร้าง PDF (บันทึกสำเร็จแล้ว ถ้า PDF พลาดก็ยังล้างฟอร์ม ป้องกันกดบันทึกซ้ำ)
        req_data = {
            "req_no": final_req_no,
            "req_date": req_date,
            "driver_name": driver,
            "vehicle_plate": vehicle,
            "customer_name": customer,
            "route_zone": route,
            "ref_bill_no": ref_bill,
            "purpose": purpose
        }
        items_snapshot = [dict(it) for it in self.cart_items]
        self.exit_edit_mode()

        try:
            pdf_path = pdf_gen.generate_requisition_pdf(
                req_data=req_data,
                items_data=items_snapshot,
                settings=inv_service.get_settings()
            )
        except Exception as e:
            messagebox.showwarning(
                "บันทึกแล้ว แต่สร้าง PDF ไม่ได้",
                f"{success_msg}\n\nแต่สร้างไฟล์ PDF ไม่สำเร็จ (อาจเปิดไฟล์ PDF เดิมค้างไว้อยู่)\n"
                f"กรุณาปิดไฟล์ PDF แล้วไปกด 'เปิดดู / พิมพ์ซ้ำ' ในหน้าประวัติ\n\nรายละเอียด: {e}"
            )
            return

        messagebox.showinfo("สำเร็จ", f"{success_msg}\nไฟล์ PDF: {pdf_path}")
        pdf_gen.open_pdf_file(pdf_path)

    # ==========================================
    # 2. VIEW: ข้อมูลรุ่นแบตเตอรี่ (Battery Models Catalog)
    # ==========================================
    def create_stock_view(self):
        view = ctk.CTkFrame(self.main_container, corner_radius=0, fg_color="transparent")
        view.grid_rowconfigure(1, weight=1)
        view.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(view, corner_radius=8)
        top_bar.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top_bar, text="🔍 ค้นหารุ่นแบตเตอรี่:").grid(row=0, column=0, padx=12, pady=10)
        self.entry_search_stock = ctk.CTkEntry(top_bar, placeholder_text="พิมพ์ยี่ห้อ (GS, FB, PUMA), รหัสรุ่น หรือขนาด Ah...")
        self.entry_search_stock.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        self.entry_search_stock.bind("<KeyRelease>", lambda e: self.refresh_stock_table())

        btn_add_product = ctk.CTkButton(
            top_bar, text="➕ เพิ่มรุ่นแบตเตอรี่ใหม่",
            fg_color="#15803d", hover_color="#166534",
            command=lambda: self.open_new_battery_dialog(for_requisition=False)
        )
        btn_add_product.grid(row=0, column=2, padx=12, pady=10)

        table_container = ctk.CTkFrame(view, corner_radius=8)
        table_container.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        self.stock_tree = ttk.Treeview(
            table_container, 
            columns=("brand", "code", "name", "capacity", "type"), 
            show="headings", 
            selectmode="browse"
        )
        self.stock_tree.heading("brand", text="ยี่ห้อ")
        self.stock_tree.heading("code", text="รหัสรุ่น")
        self.stock_tree.heading("name", text="รายละเอียด / ชื่อเต็ม")
        self.stock_tree.heading("capacity", text="ความจุ (Ah)")
        self.stock_tree.heading("type", text="ประเภท")

        self.stock_tree.column("brand", width=80, anchor="center")
        self.stock_tree.column("code", width=180, anchor="w")
        self.stock_tree.column("name", width=420, anchor="w")
        self.stock_tree.column("capacity", width=90, anchor="center")
        self.stock_tree.column("type", width=110, anchor="center")

        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.stock_tree.yview)
        self.stock_tree.configure(yscrollcommand=scrollbar.set)

        self.stock_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)

        stock_actions = ctk.CTkFrame(view, fg_color="transparent")
        stock_actions.grid(row=2, column=0, padx=16, pady=(4, 16), sticky="ew")

        btn_edit_stock = ctk.CTkButton(
            stock_actions, text="✏️ แก้ไขข้อมูลรุ่น",
            fg_color="#d97706", hover_color="#b45309", text_color="white",
            command=self.open_edit_product_dialog
        )
        btn_edit_stock.pack(side="left", padx=(0, 8))

        btn_del_stock = ctk.CTkButton(
            stock_actions, text="🗑️ ลบรุ่น",
            fg_color="#ef4444", hover_color="#dc2626",
            command=self.delete_selected_product
        )
        btn_del_stock.pack(side="left", padx=8)

        return view

    def refresh_stock_table(self):
        for row in self.stock_tree.get_children():
            self.stock_tree.delete(row)

        search = self.entry_search_stock.get()
        items = inv_service.get_all_items(search)
        for it in items:
            self.stock_tree.insert("", "end", iid=str(it["id"]), values=(
                it["brand"],
                it["item_code"],
                it["item_name"],
                it.get("capacity") or "-",
                it.get("battery_type") or "-"
            ))

    def open_edit_product_dialog(self):
        sel = self.stock_tree.selection()
        if not sel:
            messagebox.showwarning("แจ้งเตือน", "กรุณาคลิกเลือกแถวสินค้าในตารางก่อน")
            return
        item_id = int(sel[0])
        values = self.stock_tree.item(sel[0])["values"]

        dlg = ctk.CTkToplevel(self)
        dlg.title("แก้ไขข้อมูลรุ่นแบตเตอรี่")
        dlg.geometry("460x360")
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="ยี่ห้อ:").pack(anchor="w", padx=24, pady=(12, 2))
        e_brand = ctk.CTkEntry(dlg)
        e_brand.insert(0, values[0])
        e_brand.pack(fill="x", padx=24)

        ctk.CTkLabel(dlg, text="รหัสรุ่น:").pack(anchor="w", padx=24, pady=(6, 2))
        e_code = ctk.CTkEntry(dlg)
        e_code.insert(0, values[1])
        e_code.pack(fill="x", padx=24)

        ctk.CTkLabel(dlg, text="ชื่อ/รายละเอียด:").pack(anchor="w", padx=24, pady=(6, 2))
        e_name = ctk.CTkEntry(dlg)
        e_name.insert(0, values[2])
        e_name.pack(fill="x", padx=24)

        ctk.CTkLabel(dlg, text="ความจุ (Ah):").pack(anchor="w", padx=24, pady=(6, 2))
        e_cap = ctk.CTkEntry(dlg)
        e_cap.insert(0, str(values[3]))
        e_cap.pack(fill="x", padx=24)

        def save():
            brand = e_brand.get().strip().upper()
            code = e_code.get().strip()
            name = e_name.get().strip()
            if not brand or not code or not name:
                messagebox.showwarning("แจ้งเตือน", "กรุณากรอกยี่ห้อ รหัสรุ่น และชื่อให้ครบ", parent=dlg)
                return
            duplicate = inv_service.get_item_by_code(code)
            if duplicate and duplicate["id"] != item_id:
                messagebox.showwarning("แจ้งเตือน", f"รหัสรุ่น '{code}' ซ้ำกับรุ่นอื่นในระบบ", parent=dlg)
                return
            try:
                inv_service.update_item(
                    item_id=item_id,
                    brand=brand,
                    item_code=code,
                    item_name=name,
                    capacity=e_cap.get().strip(),
                    battery_type=str(values[4]),
                    unit="ลูก",
                    stock_qty=9999,
                    min_qty=0
                )
            except Exception as ex:
                messagebox.showerror("ผิดพลาด", f"บันทึกการแก้ไขไม่สำเร็จ: {ex}", parent=dlg)
                return
            dlg.destroy()
            self.refresh_stock_table()
            self.refresh_inventory_cache()

        ctk.CTkButton(dlg, text="บันทึกการแก้ไข", command=save, fg_color="#d97706", text_color="white", height=36).pack(fill="x", padx=24, pady=16)

    def delete_selected_product(self):
        sel = self.stock_tree.selection()
        if not sel:
            messagebox.showwarning("แจ้งเตือน", "กรุณาคลิกเลือกรายการที่ต้องการลบ")
            return
        values = self.stock_tree.item(sel[0])["values"]
        confirm = messagebox.askyesno("ยืนยันการลบ", f"ต้องการลบแบตเตอรี่ '{values[0]} {values[1]}' หรือไม่?")
        if confirm:
            inv_service.delete_item(int(sel[0]))
            self.refresh_stock_table()
            self.refresh_inventory_cache()

    # ==========================================
    # 3. VIEW: ประวัติและพิมพ์ซ้ำ (History View)
    # ==========================================
    def create_history_view(self):
        view = ctk.CTkFrame(self.main_container, corner_radius=0, fg_color="transparent")
        view.grid_rowconfigure(2, weight=1)
        view.grid_columnconfigure(0, weight=1)

        # ----------------------------------------------------
        # ส่วนที่ 1: แถบการ์ดสรุปยอดด่วน Real-Time (KPI Cards)
        # ----------------------------------------------------
        stats_frame = ctk.CTkFrame(view, fg_color="transparent")
        stats_frame.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="ew")
        stats_frame.grid_columnconfigure((0, 1), weight=1)

        card_today = ctk.CTkFrame(stats_frame, corner_radius=10, fg_color=("#e0f2fe", "#083344"), border_width=1, border_color=("#bae6fd", "#0e7490"))
        card_today.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkLabel(
            card_today, text="⚡ ยอดเบิกวันนี้ (Today)", 
            font=ctk.CTkFont(size=12, weight="bold"), 
            text_color=("#0369a1", "#38bdf8")
        ).pack(anchor="w", padx=14, pady=(8, 2))
        self.lbl_stat_today = ctk.CTkLabel(
            card_today, text="0 บิล | 0 ลูก", 
            font=ctk.CTkFont(size=18, weight="bold"), 
            text_color=("#0f172a", "#f8fafc")
        )
        self.lbl_stat_today.pack(anchor="w", padx=14, pady=(0, 8))

        card_filter = ctk.CTkFrame(stats_frame, corner_radius=10, fg_color=("#f1f5f9", "#1e293b"), border_width=1, border_color=("#cbd5e1", "#334155"))
        card_filter.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        ctk.CTkLabel(
            card_filter, text="📊 ยอดรวมตามเงื่อนไขที่เลือกค้นหา", 
            font=ctk.CTkFont(size=12, weight="bold"), 
            text_color=("#475569", "#94a3b8")
        ).pack(anchor="w", padx=14, pady=(8, 2))
        self.lbl_stat_filtered = ctk.CTkLabel(
            card_filter, text="0 บิล | 0 ลูก", 
            font=ctk.CTkFont(size=18, weight="bold"), 
            text_color=("#0f172a", "#f8fafc")
        )
        self.lbl_stat_filtered.pack(anchor="w", padx=14, pady=(0, 8))

        # ----------------------------------------------------
        # ส่วนที่ 2: แถบตัวกรองและค้นหาขั้นสูง (Filter Box)
        # ----------------------------------------------------
        filter_box = ctk.CTkFrame(view, corner_radius=10)
        filter_box.grid(row=1, column=0, padx=16, pady=(4, 6), sticky="ew")
        filter_box.grid_columnconfigure(0, weight=1)

        # แถวปุ่มลัดช่วงเวลาด่วน (Quick Chips)
        chips_frame = ctk.CTkFrame(filter_box, fg_color="transparent")
        chips_frame.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(chips_frame, text="ช่วงเวลาด่วน:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 8))

        self.hist_chip_buttons = {}
        self.selected_hist_chip = "all"
        for chip_name, label in [
            ("today", "📅 วันนี้"),
            ("yesterday", "📅 เมื่อวาน"),
            ("this_week", "📅 7 วันล่าสุด"),
            ("this_month", "📅 เดือนนี้"),
            ("all", "🌐 ทั้งหมด")
        ]:
            btn = ctk.CTkButton(
                chips_frame, text=label,
                height=26, width=82,
                font=ctk.CTkFont(size=11),
                fg_color="#0e7490" if chip_name == "all" else "transparent",
                text_color="white" if chip_name == "all" else ("gray20", "gray80"),
                border_width=1, border_color="#64748b",
                command=lambda cn=chip_name: self.on_select_hist_chip(cn)
            )
            btn.pack(side="left", padx=3)
            self.hist_chip_buttons[chip_name] = btn

        # แถวช่องกรองวันที่ + ลูกค้า + คำค้นหา + ปุ่ม Action
        f_row = ctk.CTkFrame(filter_box, fg_color="transparent")
        f_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(f_row, text="จากวันที่:").pack(side="left", padx=(0, 4))
        self.entry_hist_date_from = ctk.CTkEntry(f_row, width=105, placeholder_text="DD/MM/YYYY")
        self.entry_hist_date_from.pack(side="left", padx=(0, 8))
        self.entry_hist_date_from.bind("<Return>", lambda e: self.refresh_history_table())

        ctk.CTkLabel(f_row, text="ถึง:").pack(side="left", padx=(0, 4))
        self.entry_hist_date_to = ctk.CTkEntry(f_row, width=105, placeholder_text="DD/MM/YYYY")
        self.entry_hist_date_to.pack(side="left", padx=(0, 10))
        self.entry_hist_date_to.bind("<Return>", lambda e: self.refresh_history_table())

        ctk.CTkLabel(f_row, text="ร้านค้า/ลูกค้า:").pack(side="left", padx=(0, 4))
        self.combo_hist_customer = ctk.CTkComboBox(f_row, values=["ทั้งหมด"], width=170)
        self.combo_hist_customer.set("ทั้งหมด")
        self.combo_hist_customer.pack(side="left", padx=(0, 10))
        self.combo_hist_customer.configure(command=lambda e: self.refresh_history_table())

        ctk.CTkLabel(f_row, text="คำค้น:").pack(side="left", padx=(0, 4))
        self.entry_search_hist = ctk.CTkEntry(f_row, placeholder_text="เลขที่บิล, คนขับ, ทะเบียนรถ...")
        self.entry_search_hist.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_search_hist.bind("<KeyRelease>", lambda e: self.refresh_history_table())

        btn_filter = ctk.CTkButton(
            f_row, text="🔍 กรองข้อมูล",
            width=90, height=30,
            font=ctk.CTkFont(weight="bold"),
            command=self.refresh_history_table
        )
        btn_filter.pack(side="left", padx=3)

        btn_reset = ctk.CTkButton(
            f_row, text="🔄 รีเซ็ต",
            fg_color="#64748b", hover_color="#475569",
            width=65, height=30,
            command=self.reset_history_filters
        )
        btn_reset.pack(side="left", padx=3)

        self.lbl_hist_filter_error = ctk.CTkLabel(filter_box, text="", text_color="#dc2626", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_hist_filter_error.pack(anchor="w", padx=12, pady=(0, 4))

        # ----------------------------------------------------
        # ส่วนที่ 3: ตารางแสดงประวัติใบเบิก
        # ----------------------------------------------------
        table_container = ctk.CTkFrame(view, corner_radius=8)
        table_container.grid(row=2, column=0, padx=16, pady=6, sticky="nsew")
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        self.hist_tree = ttk.Treeview(
            table_container, 
            columns=("req_no", "date", "vehicle", "driver", "customer", "bill", "total_qty", "status"), 
            show="headings", 
            selectmode="browse"
        )
        self.hist_tree.heading("req_no", text="เลขที่ใบเบิก")
        self.hist_tree.heading("date", text="วันที่")
        self.hist_tree.heading("vehicle", text="ทะเบียนรถ")
        self.hist_tree.heading("driver", text="คนขับ/ผู้เบิก")
        self.hist_tree.heading("customer", text="ร้านค้า/ลูกค้า")
        self.hist_tree.heading("bill", text="บิลอ้างอิง")
        self.hist_tree.heading("total_qty", text="แบต (ลูก) / อื่นๆ")
        self.hist_tree.heading("status", text="สถานะ")

        self.hist_tree.column("req_no", width=130, anchor="center")
        self.hist_tree.column("date", width=95, anchor="center")
        self.hist_tree.column("vehicle", width=120, anchor="center")
        self.hist_tree.column("driver", width=140, anchor="w")
        self.hist_tree.column("customer", width=180, anchor="w")
        self.hist_tree.column("bill", width=100, anchor="center")
        self.hist_tree.column("total_qty", width=130, anchor="center")
        self.hist_tree.column("status", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=scrollbar.set)

        self.hist_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)

        # ----------------------------------------------------
        # ส่วนที่ 4: แถบปุ่มดำเนินการ (Actions Bar)
        # ----------------------------------------------------
        hist_actions = ctk.CTkFrame(view, fg_color="transparent")
        hist_actions.grid(row=3, column=0, padx=16, pady=(4, 14), sticky="ew")

        btn_reprint = ctk.CTkButton(
            hist_actions, text="🖨️ เปิดดู / พิมพ์ซ้ำ (A5 PDF)",
            fg_color="#0e7490", hover_color="#155e75",
            height=36,
            command=self.reprint_requisition_pdf
        )
        btn_reprint.pack(side="left", padx=(0, 8))

        btn_edit_req = ctk.CTkButton(
            hist_actions, text="✏️ แก้ไขใบเบิกนี้",
            fg_color="#d97706", hover_color="#b45309", text_color="white",
            height=36,
            command=self.load_requisition_for_edit
        )
        btn_edit_req.pack(side="left", padx=8)

        btn_cancel_req = ctk.CTkButton(
            hist_actions, text="❌ ยกเลิกใบเบิก",
            fg_color="#ef4444", hover_color="#dc2626",
            height=36,
            command=self.cancel_requisition_action
        )
        btn_cancel_req.pack(side="left", padx=8)

        btn_delete_req = ctk.CTkButton(
            hist_actions, text="🗑️ ลบใบเบิกถาวร",
            fg_color="#991b1b", hover_color="#7f1d1d",
            height=36,
            command=self.delete_requisition_action
        )
        btn_delete_req.pack(side="left", padx=8)

        btn_export = ctk.CTkButton(
            hist_actions, text="📥 ส่งออก Excel (.xlsx)",
            fg_color="#059669", hover_color="#047857",
            height=36, font=ctk.CTkFont(weight="bold"),
            command=self.export_history_excel_action
        )
        btn_export.pack(side="left", padx=8)

        btn_clear_cancelled = ctk.CTkButton(
            hist_actions, text="🧹 ล้างรายการที่ยกเลิกทั้งหมด",
            fg_color="#475569", hover_color="#334155",
            height=36,
            command=self.clear_cancelled_requisitions_action
        )
        btn_clear_cancelled.pack(side="right")

        return view

    def on_select_hist_chip(self, chip_name):
        self.selected_hist_chip = chip_name
        for cn, btn in self.hist_chip_buttons.items():
            if cn == chip_name:
                btn.configure(fg_color="#0e7490", text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=("gray20", "gray80"))

        now = datetime.now()
        today_str = now.strftime("%d/%m/%Y")

        if chip_name == "today":
            self.entry_hist_date_from.delete(0, "end")
            self.entry_hist_date_from.insert(0, today_str)
            self.entry_hist_date_to.delete(0, "end")
            self.entry_hist_date_to.insert(0, today_str)
        elif chip_name == "yesterday":
            yest_str = (now - timedelta(days=1)).strftime("%d/%m/%Y")
            self.entry_hist_date_from.delete(0, "end")
            self.entry_hist_date_from.insert(0, yest_str)
            self.entry_hist_date_to.delete(0, "end")
            self.entry_hist_date_to.insert(0, yest_str)
        elif chip_name == "this_week":
            week_str = (now - timedelta(days=6)).strftime("%d/%m/%Y")  # รวมวันนี้ = 7 วันพอดี
            self.entry_hist_date_from.delete(0, "end")
            self.entry_hist_date_from.insert(0, week_str)
            self.entry_hist_date_to.delete(0, "end")
            self.entry_hist_date_to.insert(0, today_str)
        elif chip_name == "this_month":
            month_start_str = now.strftime("01/%m/%Y")
            self.entry_hist_date_from.delete(0, "end")
            self.entry_hist_date_from.insert(0, month_start_str)
            self.entry_hist_date_to.delete(0, "end")
            self.entry_hist_date_to.insert(0, today_str)
        elif chip_name == "all":
            self.entry_hist_date_from.delete(0, "end")
            self.entry_hist_date_to.delete(0, "end")

        self.refresh_history_table()

    def reset_history_filters(self):
        self.entry_hist_date_from.delete(0, "end")
        self.entry_hist_date_to.delete(0, "end")
        self.combo_hist_customer.set("ทั้งหมด")
        self.entry_search_hist.delete(0, "end")
        self.on_select_hist_chip("all")

    def refresh_history_table(self):
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)

        date_from = self.entry_hist_date_from.get().strip() if hasattr(self, "entry_hist_date_from") else None
        date_to = self.entry_hist_date_to.get().strip() if hasattr(self, "entry_hist_date_to") else None
        customer = self.combo_hist_customer.get().strip() if hasattr(self, "combo_hist_customer") else None
        search = self.entry_search_hist.get().strip() if hasattr(self, "entry_search_hist") else None

        # อัปเดตรายชื่อลูกค้าใน Dropdown
        if hasattr(self, "combo_hist_customer"):
            curr_cust = self.combo_hist_customer.get()
            cust_list = ["ทั้งหมด"] + inv_service.get_customers_list()
            self.combo_hist_customer.configure(values=cust_list)
            if curr_cust in cust_list:
                self.combo_hist_customer.set(curr_cust)

        try:
            # ดึงทุกใบที่ตรงเงื่อนไข: ใช้ทั้งยอดสรุปและการส่งออก Excel (ตารางแสดงเฉพาะใบล่าสุด)
            self.current_filtered_reqs = inv_service.get_requisitions_advanced(
                start_date=date_from,
                end_date=date_to,
                customer=customer,
                keyword=search,
                limit=None
            )
            if hasattr(self, "lbl_hist_filter_error"):
                self.lbl_hist_filter_error.configure(text="")
        except ValueError as e:
            self.current_filtered_reqs = []
            if hasattr(self, "lbl_hist_filter_error"):
                self.lbl_hist_filter_error.configure(text=f"⚠️ {e}")

        completed_units = 0
        completed_others = 0
        completed_bills = 0
        cancelled_bills = 0

        for idx, r in enumerate(self.current_filtered_reqs):
            status_str = "✅ จ่ายของแล้ว" if r["status"] == "COMPLETED" else "❌ ยกเลิกแล้ว"
            units = int(r.get("battery_units") or 0)
            others = int(r.get("other_lines") or 0)
            if r["status"] == "COMPLETED":
                completed_units += units
                completed_others += others
                completed_bills += 1
            else:
                cancelled_bills += 1

            if idx >= HISTORY_DISPLAY_LIMIT:
                continue
            qty_text = f"{units} ลูก" + (f" + อื่นๆ {others}" if others else "")
            self.hist_tree.insert("", "end", iid=str(r["id"]), values=(
                r["req_no"],
                r["req_date"],
                r.get("vehicle_plate", "-"),
                r.get("driver_name", "-"),
                r.get("customer_name", "-"),
                r.get("ref_bill_no", "-"),
                qty_text,
                status_str
            ))

        # อัปเดตการ์ดสรุปยอด
        if hasattr(self, "lbl_stat_today"):
            today_stats = inv_service.get_today_requisitions_stats()
            self.lbl_stat_today.configure(
                text=f"{today_stats['completed_bills']} บิล ({format_totals(today_stats['completed_units'], today_stats['completed_other_lines'])})" + 
                     (f" | ยกเลิก {today_stats['cancelled_bills']} ใบ" if today_stats['cancelled_bills'] > 0 else "")
            )

        if hasattr(self, "lbl_stat_filtered"):
            shown_note = ""
            if len(self.current_filtered_reqs) > HISTORY_DISPLAY_LIMIT:
                shown_note = f" • ตารางแสดง {HISTORY_DISPLAY_LIMIT} ใบล่าสุด"
            self.lbl_stat_filtered.configure(
                text=f"{completed_bills} บิล ({format_totals(completed_units, completed_others)})" + 
                     (f" | ยกเลิก {cancelled_bills} ใบ" if cancelled_bills > 0 else "") + shown_note
            )

    def export_history_excel_action(self):
        if not hasattr(self, "current_filtered_reqs") or not self.current_filtered_reqs:
            messagebox.showwarning("แจ้งเตือน", "ไม่มีข้อมูลใบเบิกในตารางที่สามารถส่งออกได้")
            return

        date_from = self.entry_hist_date_from.get().strip()
        date_to = self.entry_hist_date_to.get().strip()
        cust = self.combo_hist_customer.get().strip()

        filter_parts = []
        if date_from and date_to:
            filter_parts.append(f"วันที่ {date_from} ถึง {date_to}")
        elif date_from:
            filter_parts.append(f"ตั้งแต่วันที่ {date_from}")
        elif date_to:
            filter_parts.append(f"ถึงวันที่ {date_to}")
        else:
            filter_parts.append("ทุกช่วงเวลา")

        if cust and cust != "ทั้งหมด":
            filter_parts.append(f"ลูกค้า: {cust}")

        filter_desc = " | ".join(filter_parts)

        try:
            excel_path = report_exporter.export_requisitions_to_excel(
                self.current_filtered_reqs,
                filter_desc=filter_desc,
                company_name=inv_service.get_settings().get("company_name") or "บริษัท คลังแบตเตอรี่และบริการ จำกัด",
            )
            report_exporter.open_exported_excel(excel_path)
            messagebox.showinfo("ส่งออกสำเร็จ", f"ส่งออกรายงาน Excel เรียบร้อยแล้ว:\n{os.path.basename(excel_path)}")
        except Exception as e:
            messagebox.showerror("เกิดข้อผิดพลาดในการส่งออก Excel", str(e))

    def reprint_requisition_pdf(self):
        sel = self.hist_tree.selection()
        if not sel:
            messagebox.showwarning("แจ้งเตือน", "กรุณาคลิกเลือกใบเบิกในตารางก่อน")
            return
        req_id = int(sel[0])
        req, items = inv_service.get_requisition_by_id(req_id)
        if not req:
            messagebox.showerror("ผิดพลาด", "ไม่พบข้อมูลใบเบิกนี้")
            return

        try:
            pdf_path = pdf_gen.generate_requisition_pdf(req, items, inv_service.get_settings())
        except Exception as e:
            messagebox.showerror(
                "สร้าง PDF ไม่สำเร็จ",
                f"สร้างไฟล์ PDF ของใบเบิก {req['req_no']} ไม่สำเร็จ\n"
                f"ถ้าเปิดไฟล์ PDF นี้ค้างไว้อยู่ กรุณาปิดก่อนแล้วลองใหม่\n\nรายละเอียด: {e}"
            )
            return
        pdf_gen.open_pdf_file(pdf_path)

    def load_requisition_for_edit(self):
        sel = self.hist_tree.selection()
        if not sel:
            messagebox.showwarning("แจ้งเตือน", "กรุณาคลิกเลือกใบเบิกที่ต้องการแก้ไข")
            return
        req_id = int(sel[0])
        req, items = inv_service.get_requisition_by_id(req_id)
        if not req:
            messagebox.showerror("ผิดพลาด", "ไม่พบข้อมูลใบเบิกนี้")
            return
        if req["status"] == "CANCELLED":
            messagebox.showinfo("แจ้งเตือน", "ใบเบิกนี้ถูกยกเลิกไปแล้ว ไม่สามารถแก้ไขได้")
            return

        self.editing_req_id = req_id

        # สลับไปหน้าออกใบเบิก
        self.show_frame("req")

        # ใส่ข้อมูลในฟอร์ม
        self.entry_req_no.delete(0, "end")
        self.entry_req_no.insert(0, req["req_no"])
        self.entry_req_date.delete(0, "end")
        self.entry_req_date.insert(0, req["req_date"])
        self.entry_vehicle.delete(0, "end")
        self.entry_vehicle.insert(0, req["vehicle_plate"])
        self.entry_driver.delete(0, "end")
        self.entry_driver.insert(0, req["driver_name"])
        self.entry_customer.delete(0, "end")
        self.entry_customer.insert(0, req["customer_name"])
        self.combo_route.set(req.get("route_zone", ""))
        self.entry_ref_bill.delete(0, "end")
        self.entry_ref_bill.insert(0, req.get("ref_bill_no", ""))
        self.entry_purpose.delete(0, "end")
        self.entry_purpose.insert(0, req.get("purpose", ""))

        # ใส่รายการสินค้าลงตะกร้า
        self.cart_items = [dict(it) for it in items]
        self.render_cart_items()

        # แสดงแถบโหมดแก้ไข
        self.lbl_edit_banner.configure(
            text=f"🔧 โหมดแก้ไขใบเบิก: {req['req_no']} (ปรับข้อมูลขนส่ง หรือเปลี่ยนจำนวนลูก แล้วกดบันทึก)"
        )
        self.edit_banner_frame.grid(row=0, column=0, padx=14, pady=(10, 0), sticky="ew")
        self.btn_save_pdf.configure(text="💾 บันทึกการแก้ไข (Update PDF)", fg_color="#d97706", hover_color="#b45309")

    def cancel_requisition_action(self):
        sel = self.hist_tree.selection()
        if not sel:
            messagebox.showwarning("แจ้งเตือน", "กรุณาคลิกเลือกใบเบิกที่ต้องการยกเลิก")
            return
        req_id = int(sel[0])
        values = self.hist_tree.item(sel[0])["values"]

        if "ยกเลิกแล้ว" in str(values[7]):
            messagebox.showinfo("แจ้งเตือน", "ใบเบิกนี้ถูกยกเลิกไปแล้ว")
            return

        confirm = messagebox.askyesno(
            "ยืนยันการยกเลิก", 
            f"ต้องการยกเลิกใบเบิกเลขที่ {values[0]} หรือไม่?"
        )
        if confirm:
            try:
                inv_service.cancel_requisition(req_id)
                messagebox.showinfo("สำเร็จ", f"ยกเลิกใบเบิก {values[0]} เรียบร้อยแล้ว")
                self.refresh_history_table()
            except Exception as e:
                messagebox.showerror("ผิดพลาด", str(e))

    def delete_requisition_action(self):
        sel = self.hist_tree.selection()
        if not sel:
            messagebox.showwarning("แจ้งเตือน", "กรุณาคลิกเลือกใบเบิกที่ต้องการลบ")
            return
        req_id = int(sel[0])
        values = self.hist_tree.item(sel[0])["values"]

        confirm = messagebox.askyesno(
            "ยืนยันการลบถาวร", 
            f"คำเตือน: ต้องการลบใบเบิกเลขที่ {values[0]} ออกจากระบบอย่างถาวรหรือไม่?\n(ข้อมูลจะไม่สามารถกู้คืนได้)",
            icon="warning"
        )
        if confirm:
            try:
                inv_service.delete_requisition(req_id)
                messagebox.showinfo("สำเร็จ", f"ลบใบเบิก {values[0]} ออกจากระบบแล้ว")
                self.refresh_history_table()
            except Exception as e:
                messagebox.showerror("ผิดพลาด", str(e))

    def clear_cancelled_requisitions_action(self):
        confirm = messagebox.askyesno(
            "ยืนยันการล้างประวัติที่ยกเลิก",
            "ต้องการลบใบเบิกที่มีสถานะ 'ยกเลิกแล้ว' ทั้งหมดออกจากระบบหรือไม่?",
            icon="warning"
        )
        if confirm:
            try:
                deleted = inv_service.clear_cancelled_requisitions()
                messagebox.showinfo("สำเร็จ", f"ล้างใบเบิกที่ยกเลิกแล้ว {deleted} ใบ เรียบร้อยแล้ว")
                self.refresh_history_table()
            except Exception as e:
                messagebox.showerror("ผิดพลาด", str(e))

    # ==========================================
    # 4. VIEW: ตั้งค่าระบบ (Settings View)
    # ==========================================
    def create_settings_view(self):
        view = ctk.CTkScrollableFrame(self.main_container, corner_radius=0, fg_color="transparent")
        view.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(view, corner_radius=10)
        card.pack(fill="x", padx=20, pady=20)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="⚙️ ตั้งค่าหัวเอกสารและช่องลงนาม (A5 Landscape)", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 14)
        )

        ctk.CTkLabel(card, text="ชื่อบริษัท / คลังสินค้า:").grid(row=1, column=0, sticky="w", padx=20, pady=8)
        self.set_company = ctk.CTkEntry(card, width=380)
        self.set_company.grid(row=1, column=1, sticky="ew", padx=(10, 20), pady=8)

        ctk.CTkLabel(card, text="ชื่อหัวเอกสาร:").grid(row=2, column=0, sticky="w", padx=20, pady=8)
        self.set_slip_title = ctk.CTkEntry(card, width=380)
        self.set_slip_title.grid(row=2, column=1, sticky="ew", padx=(10, 20), pady=8)

        ctk.CTkLabel(card, text="ช่องลงนามที่ 1 (ซ้าย):").grid(row=3, column=0, sticky="w", padx=20, pady=8)
        self.set_role1 = ctk.CTkEntry(card, width=380)
        self.set_role1.grid(row=3, column=1, sticky="ew", padx=(10, 20), pady=8)

        ctk.CTkLabel(card, text="ช่องลงนามที่ 2 (กลาง):").grid(row=4, column=0, sticky="w", padx=20, pady=8)
        self.set_role2 = ctk.CTkEntry(card, width=380)
        self.set_role2.grid(row=4, column=1, sticky="ew", padx=(10, 20), pady=8)

        ctk.CTkLabel(card, text="ช่องลงนามที่ 3 (ขวา):").grid(row=5, column=0, sticky="w", padx=20, pady=8)
        self.set_role3 = ctk.CTkEntry(card, width=380)
        self.set_role3.grid(row=5, column=1, sticky="ew", padx=(10, 20), pady=8)

        btn_save_settings = ctk.CTkButton(
            card, text="💾 บันทึกการตั้งค่า",
            fg_color="#15803d", hover_color="#166534",
            height=38,
            command=self.save_settings
        )
        btn_save_settings.grid(row=6, column=0, columnspan=2, sticky="e", padx=20, pady=(16, 20))

        folder_card = ctk.CTkFrame(view, corner_radius=10)
        folder_card.pack(fill="x", padx=20, pady=(0, 20))
        folder_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(folder_card, text="📁 โฟลเดอร์เก็บเอกสาร PDF", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 6)
        )
        pdf_dir_path = app_paths.pdf_dir()
        ctk.CTkLabel(folder_card, text=f"ที่อยู่โฟลเดอร์: {pdf_dir_path}", text_color="gray").grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 10)
        )

        btn_open_folder = ctk.CTkButton(
            folder_card, text="📂 เปิดโฟลเดอร์ PDF",
            fg_color="#475569", hover_color="#334155",
            command=lambda: pdf_gen.open_pdf_file(pdf_dir_path)
        )
        btn_open_folder.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 16))

        # การ์ดจัดการฐานข้อมูล SQLite
        db_card = ctk.CTkFrame(view, corner_radius=10)
        db_card.pack(fill="x", padx=20, pady=(0, 20))
        db_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(db_card, text="💾 สถานะและการจัดการฐานข้อมูล SQLite", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 10)
        )

        ctk.CTkLabel(db_card, text="ประเภทฐานข้อมูล:").grid(row=1, column=0, sticky="w", padx=20, pady=4)
        ctk.CTkLabel(db_card, text="SQLite 3 (Local Database)", font=ctk.CTkFont(weight="bold"), text_color="#0e7490").grid(row=1, column=1, sticky="w", padx=(10, 20), pady=4)

        ctk.CTkLabel(db_card, text="สถานะการเชื่อมต่อ:").grid(row=2, column=0, sticky="w", padx=20, pady=4)
        self.lbl_db_status = ctk.CTkLabel(db_card, text="🟢 เชื่อมต่อสมบูรณ์ (Connected)", text_color="#15803d", font=ctk.CTkFont(weight="bold"))
        self.lbl_db_status.grid(row=2, column=1, sticky="w", padx=(10, 20), pady=4)

        ctk.CTkLabel(db_card, text="ตำแหน่งไฟล์ .db:").grid(row=3, column=0, sticky="w", padx=20, pady=4)
        self.lbl_db_path = ctk.CTkLabel(db_card, text="", text_color="gray")
        self.lbl_db_path.grid(row=3, column=1, sticky="w", padx=(10, 20), pady=4)

        ctk.CTkLabel(db_card, text="สถิติข้อมูลในระบบ:").grid(row=4, column=0, sticky="w", padx=20, pady=4)
        self.lbl_db_stats = ctk.CTkLabel(db_card, text="", font=ctk.CTkFont(size=12))
        self.lbl_db_stats.grid(row=4, column=1, sticky="w", padx=(10, 20), pady=4)

        db_btn_frame = ctk.CTkFrame(db_card, fg_color="transparent")
        db_btn_frame.grid(row=5, column=0, columnspan=2, sticky="w", padx=20, pady=(12, 16))

        btn_backup = ctk.CTkButton(
            db_btn_frame, text="📦 สำรองฐานข้อมูล (Backup .db)",
            fg_color="#0e7490", hover_color="#155e75", height=34,
            command=self.do_backup_database
        )
        btn_backup.pack(side="left", padx=(0, 10))

        btn_open_db = ctk.CTkButton(
            db_btn_frame, text="📂 เปิดตำแหน่งไฟล์ SQLite",
            fg_color="#475569", hover_color="#334155", height=34,
            command=self.open_db_folder
        )
        btn_open_db.pack(side="left", padx=10)

        return view

    def do_backup_database(self):
        try:
            backup_path = inv_service.backup_database()
            messagebox.showinfo("สำรองฐานข้อมูลสำเร็จ", f"สำรองข้อมูล SQLite เรียบร้อยแล้วที่:\n{backup_path}")
            self.load_settings()
        except Exception as e:
            messagebox.showerror("เกิดข้อผิดพลาด", str(e))

    def open_db_folder(self):
        db_info = inv_service.get_db_info()
        folder = os.path.dirname(db_info["db_path"])
        pdf_gen.open_pdf_file(folder)

    def load_settings(self):
        settings = inv_service.get_settings()
        self.set_company.delete(0, "end")
        self.set_company.insert(0, settings.get("company_name", ""))

        self.set_slip_title.delete(0, "end")
        self.set_slip_title.insert(0, settings.get("slip_title", ""))

        self.set_role1.delete(0, "end")
        self.set_role1.insert(0, settings.get("sign_role_1", ""))

        self.set_role2.delete(0, "end")
        self.set_role2.insert(0, settings.get("sign_role_2", ""))

        self.set_role3.delete(0, "end")
        self.set_role3.insert(0, settings.get("sign_role_3", ""))

        # อัปเดตข้อมูล SQLite
        db_info = inv_service.get_db_info()
        self.lbl_db_path.configure(text=f"{db_info['db_path']} (ขนาด {db_info['size_kb']})")
        self.lbl_db_stats.configure(
            text=f"แบตเตอรี่ในคลัง {db_info['item_count']} รุ่น | มีใบเบิกสะสมในระบบ {db_info['req_count']} ใบ"
        )

    def save_settings(self):
        new_settings = {
            "company_name": self.set_company.get().strip(),
            "slip_title": self.set_slip_title.get().strip(),
            "sign_role_1": self.set_role1.get().strip(),
            "sign_role_2": self.set_role2.get().strip(),
            "sign_role_3": self.set_role3.get().strip(),
        }
        inv_service.update_settings(new_settings)
        messagebox.showinfo("สำเร็จ", "บันทึกการตั้งค่าเรียบร้อยแล้ว")

if __name__ == "__main__":
    app = BatteryRequisitionApp()
    app.mainloop()
