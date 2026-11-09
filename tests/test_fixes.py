import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

import openpyxl

import app_paths
from services.catalog_rules import build_base_code, detect_brand
from services.categories import BATTERY, count_breakdown, format_breakdown, item_category, summarize_items
from services.dates import normalize_req_date, to_iso_date

BATTERY_LINE = {"item_id": 1, "brand": "FB", "item_code": "FB N100", "item_name": "แบตเตอรี่ FB N100",
                "capacity": "100 Ah", "unit": "ลูก", "quantity": 4, "remark": "", "category": BATTERY}
PART_LINE = {"item_id": None, "brand": "อะไหล่", "item_code": "ขั้วแบต", "item_name": "ขั้วแบต",
             "capacity": "-", "unit": "ตัว", "quantity": 2, "remark": "", "category": "อะไหล่"}


class TempHomeTestCase(unittest.TestCase):
    """ทุกไฟล์ที่โปรแกรมเขียนจะไปอยู่ในโฟลเดอร์ชั่วคราว ไม่แตะข้อมูลจริง"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name
        self._env = mock.patch.dict(os.environ, {app_paths.HOME_ENV: self.home})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class BrandDetectionTests(unittest.TestCase):
    def test_efb_is_not_read_as_brand_fb(self):
        self.assertEqual(detect_brand("แบตเตอรี่ GS รุ่น EVS-N55L (EFB)"), "GS")
        self.assertEqual(build_base_code("แบตเตอรี่ GS รุ่น EVS-N55L (EFB)", "GS"), "GS EVS-N55L (EFB)")

    def test_model_number_containing_fb_keeps_real_brand(self):
        self.assertEqual(detect_brand("แบตเตอรี่ BOLIDEN SILVERTECH รุ่น 12FB 75-SMF (DIN75)"), "BOLIDEN")

    def test_plain_brand_and_unknown(self):
        self.assertEqual(detect_brand("FB N100"), "FB")
        self.assertEqual(detect_brand("แบตเตอรี่แห้งไฟฉุกเฉิน 12V5A"), "ทั่วไป")


class DateTests(unittest.TestCase):
    def test_accepts_short_padded_and_buddhist_year(self):
        self.assertEqual(normalize_req_date("3/9/2026"), "03/09/2026")
        self.assertEqual(normalize_req_date("03-09-2026"), "03/09/2026")
        self.assertEqual(normalize_req_date("3/9/2569"), "03/09/2026")
        self.assertEqual(normalize_req_date("2026-09-03"), "03/09/2026")

    def test_rejects_invalid_dates(self):
        for bad in ("31/02/2026", "hello", "3/9/26"):
            with self.assertRaises(ValueError):
                normalize_req_date(bad)

    def test_filter_blank_is_none(self):
        self.assertIsNone(to_iso_date("  "))
        self.assertEqual(to_iso_date("1/11/2569"), "2026-11-01")


class CategoryTests(unittest.TestCase):
    def test_battery_units_exclude_parts(self):
        self.assertEqual(summarize_items([BATTERY_LINE, PART_LINE]), (4, 1))

    def test_legacy_rows_without_category(self):
        self.assertEqual(item_category({"item_id": 5, "brand": "อะไหล่"}), BATTERY)
        self.assertEqual(item_category({"item_id": None, "brand": "อะไหล่", "item_name": "ขั้วแบต"}), "อะไหล่")
        self.assertEqual(item_category({"item_id": None, "brand": "ทั่วไป", "item_name": "แบตเตอรี่แห้ง 12V"}), BATTERY)


class CountBreakdownTests(unittest.TestCase):
    def test_batteries_total_then_each_other_item_with_its_unit(self):
        items = [
            BATTERY_LINE,
            dict(BATTERY_LINE, item_id=2, quantity=8),
            dict(PART_LINE, item_name="ขั้วแบต", unit="อัน", quantity=2),
            dict(PART_LINE, item_name="น้ำกลั่น", unit="ขวด", quantity=3, category="น้ำกลั่น/เคมี"),
            dict(PART_LINE, item_name="ขั้วแบต", unit="อัน", quantity=1),
        ]
        self.assertEqual(count_breakdown(items), [(BATTERY, 12, "ลูก"), ("ขั้วแบต", 3, "อัน"), ("น้ำกลั่น", 3, "ขวด")])
        self.assertEqual(format_breakdown(count_breakdown(items)), "แบตเตอรี่ 12 ลูก | ขั้วแบต 3 อัน | น้ำกลั่น 3 ขวด")

    def test_same_name_different_unit_stays_separate_and_no_battery_row_when_none(self):
        items = [dict(PART_LINE, unit="ตัว"), dict(PART_LINE, unit="ชุด")]
        self.assertEqual(count_breakdown(items), [("ขั้วแบต", 2, "ตัว"), ("ขั้วแบต", 2, "ชุด")])


class PdfCountSummaryTests(unittest.TestCase):
    def _fit(self, items):
        from services.pdf_generator import BatteryRequisitionPDF, _fit_count_summary
        pdf = BatteryRequisitionPDF()
        pdf.add_page()
        return _fit_count_summary(pdf, items, width=186)

    def test_typical_bill_fits_one_line_at_normal_size(self):
        size, lines = self._fit([BATTERY_LINE, dict(PART_LINE, unit="อัน")])
        self.assertEqual((size, len(lines)), (9, 1))
        self.assertIn("แบตเตอรี่ 4 ลูก | ขั้วแบต 2 อัน", lines[0])

    def test_fifteen_long_part_names_still_list_every_item_within_three_lines(self):
        items = [dict(PART_LINE, item_name=f"ไดชาร์จโตโยต้าวีโก้ 80A รีบิลด์พร้อมมู่เล่ รุ่นที่ {i}", unit="ตัว", quantity=i)
                 for i in range(1, 16)]
        size, lines = self._fit(items)
        self.assertLessEqual(len(lines), 3)
        text = " ".join(lines)
        for i in range(1, 16):
            self.assertIn(f" {i} ตัว", text)


class FreshInstallTests(TempHomeTestCase):
    def test_first_run_imports_catalog_into_the_database_the_app_uses(self):
        from database.db import get_db_file, init_db
        from services import inventory_service as inv

        init_db()
        self.assertTrue(get_db_file().startswith(self.home))
        items = inv.get_all_items()
        self.assertGreater(len(items), 300)
        gs_efb = inv.get_item_by_code("GS EVS-N55L (EFB)")
        self.assertIsNotNone(gs_efb)
        self.assertEqual(gs_efb["brand"], "GS")
        self.assertFalse(any(it["item_code"].startswith("FB GS ") for it in items))


class RequisitionServiceTests(TempHomeTestCase):
    def setUp(self):
        super().setUp()
        from database.db import get_db_file
        from database.migrations import run_migrations
        run_migrations(get_db_file())
        from services import inventory_service as inv
        self.inv = inv
        battery_id = inv.add_item("FB", "FB N100", "แบตเตอรี่ FB N100", "100 Ah")
        self.assertEqual(battery_id, BATTERY_LINE["item_id"])

    def _create(self, items=None, req_date="3/9/2569", req_no=None):
        return self.inv.create_requisition("คนขับ", "1กข-1234", "ร้าน ก", "", "", "",
                                           items or [BATTERY_LINE, PART_LINE], custom_req_no=req_no, req_date=req_date)

    def test_totals_count_batteries_and_other_lines_separately(self):
        req_id, _ = self._create()
        rows = self.inv.get_requisitions_advanced()
        self.assertEqual((rows[0]["battery_units"], rows[0]["other_lines"]), (4, 1))
        _, items = self.inv.get_requisition_by_id(req_id)
        self.assertEqual([it["category"] for it in items], [BATTERY, "อะไหล่"])

    def test_date_is_stored_normalized_and_filter_accepts_buddhist_year(self):
        req_id, _ = self._create(req_date="3/9/2569")
        req, _ = self.inv.get_requisition_by_id(req_id)
        self.assertEqual(req["req_date"], "03/09/2026")
        self.assertEqual(len(self.inv.get_requisitions_advanced(start_date="1/9/2569", end_date="30/9/2569")), 1)
        self.assertEqual(len(self.inv.get_requisitions_advanced(start_date="01/10/2026")), 0)

    def test_invalid_date_is_rejected_before_saving(self):
        with self.assertRaises(ValueError):
            self._create(req_date="31/02/2026")
        self.assertEqual(self.inv.get_requisitions_advanced(), [])

    def test_delete_requisition_and_number_is_not_reused(self):
        from database.db import generate_next_req_no
        first_no = generate_next_req_no()
        req_id, saved_no = self._create(req_no=first_no)
        self.inv.delete_requisition(req_id)
        self.assertEqual(self.inv.get_requisition_by_id(req_id), (None, []))
        self.assertNotEqual(generate_next_req_no(), saved_no)

    def test_clear_cancelled_only_removes_cancelled(self):
        keep_id, _ = self._create()
        drop_id, _ = self._create()
        self.inv.cancel_requisition(drop_id)
        self.assertEqual(self.inv.clear_cancelled_requisitions(), 1)
        self.assertEqual([r["id"] for r in self.inv.get_requisitions_advanced()], [keep_id])

    def test_duplicate_requisition_number_gives_readable_error(self):
        self._create(req_no="REQ-202611-0007")
        with self.assertRaisesRegex(ValueError, "มีอยู่ในระบบแล้ว"):
            self._create(req_no="REQ-202611-0007")

    def test_no_200_row_cap_for_totals(self):
        for _ in range(205):
            self._create(items=[BATTERY_LINE])
        rows = self.inv.get_requisitions_advanced()
        self.assertEqual(len(rows), 205)
        self.assertEqual(sum(r["battery_units"] for r in rows), 205 * 4)

    def test_excel_export_splits_battery_and_other_columns(self):
        from services.report_export import export_requisitions_to_excel
        self._create()
        path = export_requisitions_to_excel(self.inv.get_requisitions_advanced())
        self.assertTrue(path.startswith(self.home))
        ws = openpyxl.load_workbook(path).active
        self.assertEqual(ws.cell(row=5, column=9).value, "แบตเตอรี่ (ลูก)")
        self.assertEqual(ws.cell(row=5, column=10).value, "อื่นๆ (รายการ)")
        self.assertEqual((ws.cell(row=6, column=9).value, ws.cell(row=6, column=10).value), (4, 1))

    def test_pdf_works_from_any_working_directory(self):
        from services.pdf_generator import generate_requisition_pdf
        old_cwd = os.getcwd()
        os.chdir(self.home)
        try:
            path = generate_requisition_pdf({"req_no": "REQ-202611-0001", "req_date": "03/09/2026"},
                                            [BATTERY_LINE, PART_LINE])
        finally:
            os.chdir(old_cwd)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.startswith(self.home))


class MigrationV2Tests(TempHomeTestCase):
    def test_upgrades_v1_database(self):
        from database.migrations import migration_v1, run_migrations
        db_path = os.path.join(self.home, "old.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        migration_v1(cur)
        cur.execute("PRAGMA user_version = 1")
        name = "แบตเตอรี่ GS รุ่น EVS-N55L (EFB)"
        cur.execute("INSERT INTO items (brand, item_code, item_name) VALUES ('FB', 'FB GS รุ่น EVS-N55L (EFB)', ?)", (name,))
        cur.execute("INSERT INTO items (brand, item_code, item_name) VALUES ('BOLIDEN', 'BOLIDEN X', 'แบตเตอรี่ BOLIDEN รุ่น 12FB 75')")
        cur.execute("INSERT INTO requisitions (req_no, req_date, driver_name, vehicle_plate, customer_name) VALUES ('REQ-202609-0001', '3/9/2026', '-', '-', 'ร้าน')")
        cur.execute("INSERT INTO requisition_items (requisition_id, item_id, brand, item_code, item_name, quantity) VALUES (1, 1, 'FB', 'x', 'x', 2)")
        cur.execute("INSERT INTO requisition_items (requisition_id, item_id, brand, item_code, item_name, unit, quantity) VALUES (1, NULL, 'อะไหล่', 'ขั้วแบต', 'ขั้วแบต', 'ตัว', 3)")
        conn.commit()
        conn.close()

        run_migrations(db_path)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        self.assertEqual(cur.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(cur.execute("SELECT brand, item_code FROM items WHERE id = 1").fetchone(), ("GS", "GS EVS-N55L (EFB)"))
        self.assertEqual(cur.execute("SELECT brand FROM items WHERE id = 2").fetchone()[0], "BOLIDEN")
        self.assertEqual([r[0] for r in cur.execute("SELECT category FROM requisition_items ORDER BY id")], [BATTERY, "อะไหล่"])
        self.assertEqual(cur.execute("SELECT req_date FROM requisitions").fetchone()[0], "03/09/2026")
        conn.close()
        self.assertTrue(os.listdir(os.path.join(self.home, "database_backups")))


class WindowsInstallPathTests(unittest.TestCase):
    def test_frozen_windows_uses_localappdata_and_moves_old_installer_data(self):
        from database.db import ensure_data_directory, get_db_file
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = os.path.join(tmp, "Program Files", "BatteryRequisitionApp")
            os.makedirs(os.path.join(app_dir, "data"))
            legacy = os.path.join(app_dir, "data", "inventory.db")
            conn = sqlite3.connect(legacy)
            conn.execute("CREATE TABLE marker (v TEXT)")
            conn.execute("INSERT INTO marker VALUES ('old data')")
            conn.commit()
            conn.close()
            local = os.path.join(tmp, "Local")
            env = {k: v for k, v in os.environ.items() if k != app_paths.HOME_ENV}
            env["LOCALAPPDATA"] = local
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.object(sys, "executable", os.path.join(app_dir, "BatteryRequisition.exe")), \
                    mock.patch.object(sys, "_MEIPASS", os.path.join(app_dir, "_internal"), create=True):
                self.assertEqual(get_db_file(), os.path.join(local, "BatteryRequisition", "data", "inventory.db"))
                self.assertEqual(app_paths.font_file("Sarabun-Bold.ttf"),
                                 os.path.join(app_dir, "_internal", "assets", "fonts", "Sarabun-Bold.ttf"))
                ensure_data_directory()
                conn = sqlite3.connect(get_db_file())
                self.assertEqual(conn.execute("SELECT v FROM marker").fetchone()[0], "old data")
                conn.close()


if __name__ == "__main__":
    unittest.main()
