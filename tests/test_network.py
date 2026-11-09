import os
import tempfile
import threading
import unittest
from unittest import mock

import app_paths
from services import netconfig
from services.errors import AuthError, ConflictError, ServerUnavailable
from services.remote import RemoteClient, discover
from services.server import start_server

BATTERY = {"item_id": None, "brand": "FB", "item_code": "FB N100", "item_name": "แบตเตอรี่ FB N100",
           "capacity": "100 Ah", "unit": "ลูก", "quantity": 2, "remark": "", "category": "แบตเตอรี่"}
PART = {"item_id": None, "brand": "อะไหล่", "item_code": "ขั้วแบต", "item_name": "ขั้วแบต",
        "capacity": "-", "unit": "อัน", "quantity": 3, "remark": "", "category": "อะไหล่"}


class LanTestCase(unittest.TestCase):
    """เปิดเซิร์ฟเวอร์จริงบนพอร์ตสุ่ม (127.0.0.1) พร้อมฐานข้อมูลชั่วคราว"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {app_paths.HOME_ENV: self._tmp.name})
        self._env.start()
        from database.db import get_db_file
        from database.migrations import run_migrations
        run_migrations(get_db_file())
        self.token = "123456"
        self.server, self.stop = start_server(0, self.token, bind_host="127.0.0.1", discovery_port=0, background_jobs=False)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.client = RemoteClient("127.0.0.1", self.port, self.token)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.stop.set()
        self._env.stop()
        self._tmp.cleanup()

    def create(self, client=None, items=None, **kw):
        c = client or self.client
        return c.call("create_requisition", "คนขับ", "1กข-1", "ร้าน ก", "", "", "", items or [BATTERY, PART], **kw)


class RpcTests(LanTestCase):
    def test_ping_needs_no_token_and_rpc_needs_token(self):
        self.assertTrue(RemoteClient("127.0.0.1", self.port, "").ping())
        with self.assertRaises(AuthError):
            RemoteClient("127.0.0.1", self.port, "000000").call("get_settings")
        self.assertIsNone(self.client.check())
        self.assertIn("รหัสเชื่อมต่อไม่ถูกต้อง", RemoteClient("127.0.0.1", self.port, "bad").check())

    def test_unreachable_server_raises_readable_error(self):
        with self.assertRaises(ServerUnavailable):
            RemoteClient("127.0.0.1", 1, "x", timeout=1).call("get_settings")

    def test_only_whitelisted_functions_can_be_called(self):
        with self.assertRaisesRegex(ValueError, "ไม่รู้จักคำสั่ง"):
            self.client.call("get_connection")

    def test_data_round_trip_and_error_types(self):
        req_id, req_no = self.create(req_date="3/9/2569")
        req, items = self.client.call("get_requisition_by_id", req_id)
        self.assertEqual((req["req_date"], req["version"], len(items)), ("03/09/2026", 1, 2))
        self.assertEqual([i["category"] for i in items], ["แบตเตอรี่", "อะไหล่"])
        with self.assertRaises(ValueError):  # ชนิดข้อผิดพลาดถูกส่งกลับมาให้หน้าจอจับได้เหมือนใช้เครื่องเดียว
            self.create(req_date="31/02/2026")


class ConcurrencyTests(LanTestCase):
    def test_three_machines_saving_at_the_same_time_get_distinct_numbers(self):
        clients = [RemoteClient("127.0.0.1", self.port, self.token) for _ in range(3)]
        shown = self.client.call("next_req_no")  # ทั้ง 3 เครื่องเห็นเลขเดียวกันบนหน้าจอ
        numbers, errors = [], []

        def worker(c):
            try:
                for _ in range(5):
                    numbers.append(self.create(c, custom_req_no=shown)[1])
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(numbers), 15)
        self.assertEqual(len(set(numbers)), 15)
        self.assertEqual(len(self.client.call("get_requisitions_advanced")), 15)

    def test_edit_conflict_is_detected_not_overwritten(self):
        req_id, _ = self.create()
        a = self.client.call("get_requisition_by_id", req_id)[0]
        b = self.client.call("get_requisition_by_id", req_id)[0]
        self.assertEqual((a["version"], b["version"]), (1, 1))
        args = ("คนขับ", "1กข-1", "ร้าน A", "", "", "", [BATTERY])
        self.client.call("update_requisition", req_id, *args, expected_version=a["version"])
        with self.assertRaises(ConflictError) as ctx:
            self.client.call("update_requisition", req_id, "คนขับ", "1กข-1", "ร้าน B", "", "", "", [BATTERY],
                             expected_version=b["version"])
        self.assertIn("ถูกแก้ไขหรือยกเลิกโดยเครื่องอื่น", str(ctx.exception))
        self.assertEqual(self.client.call("get_requisition_by_id", req_id)[0]["customer_name"], "ร้าน A")

    def test_editing_a_bill_that_another_machine_cancelled_is_blocked(self):
        req_id, _ = self.create()
        version = self.client.call("get_requisition_by_id", req_id)[0]["version"]
        self.client.call("cancel_requisition", req_id)
        with self.assertRaises(ConflictError):
            self.client.call("update_requisition", req_id, "x", "x", "x", "", "", "", [BATTERY], expected_version=version)

    def test_new_battery_model_added_on_one_machine_is_visible_to_another(self):
        self.client.call("add_item", "FB", "FB N999", "แบตเตอรี่ FB N999", "-", "-", "ลูก", 9999, 0, category="แบตเตอรี่")
        other = RemoteClient("127.0.0.1", self.port, self.token)
        self.assertEqual(other.call("get_item_by_code", "FB N999")["brand"], "FB")


class DiscoveryAndConfigTests(unittest.TestCase):
    def test_discovery_finds_server(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {app_paths.HOME_ENV: tmp}):
            from database.db import get_db_file
            from database.migrations import run_migrations
            run_migrations(get_db_file())
            probe = __import__("socket").socket(__import__("socket").AF_INET, __import__("socket").SOCK_DGRAM)
            probe.bind(("127.0.0.1", 0))
            disc_port = probe.getsockname()[1]
            probe.close()
            server, stop = start_server(0, "1", bind_host="127.0.0.1", discovery_port=disc_port, background_jobs=False)
            try:
                found = discover(timeout=1.0, broadcast="127.0.0.1", port=disc_port)
            finally:
                stop.set()
                server.server_close()
            self.assertEqual([f["host"] for f in found], ["127.0.0.1"])
            self.assertEqual(found[0]["port"], server.server_address[1])

    def test_discovery_prefers_real_address_over_loopback(self):
        from services import remote
        replies = [
            (b'{"app": "battery-requisition", "port": 8765, "name": "PC1"}', ("127.0.0.1", 8766)),
            (b'{"app": "battery-requisition", "port": 8765, "name": "PC1"}', ("192.168.1.20", 8766)),
        ]
        queue = list(replies)

        def recvfrom(_size):
            if queue:
                return queue.pop(0)
            raise __import__("socket").timeout()

        fake = mock.MagicMock()
        fake.recvfrom.side_effect = recvfrom
        with mock.patch.object(remote.socket, "socket", return_value=fake):
            found = remote.discover(timeout=0.5, broadcast="192.168.1.255")
        self.assertEqual([f["host"] for f in found], ["192.168.1.20"])

    def test_config_round_trip_and_default(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {app_paths.HOME_ENV: tmp}):
            self.assertIsNone(netconfig.load())
            self.assertEqual(netconfig.effective(None)["mode"], "standalone")
            netconfig.save({"mode": "client", "host": "192.168.1.5", "port": 8765, "token": "654321"})
            self.assertEqual(netconfig.load()["host"], "192.168.1.5")
            self.assertEqual(len(netconfig.new_token()), 6)


if __name__ == "__main__":
    unittest.main()
