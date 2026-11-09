"""ฝั่งเครื่องลูก: เรียก inventory_service ของเครื่องหลักผ่านวงแลนด์ + ค้นหาเครื่องหลัก"""
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import app_paths
from services import netconfig
from services.errors import AuthError, ConflictError, ServerUnavailable
from services.server import APP_ID, DISCOVER_MESSAGE

_ERROR_TYPES = {"ValueError": ValueError, "ConflictError": ConflictError}
# ไม่ใช้พร็อกซีของระบบ: คำขอวงแลนด์ต้องไม่ถูกส่งออกไปทางพร็อกซีของบริษัท/อินเทอร์เน็ต
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class RemoteClient:
    def __init__(self, host, port, token, timeout=10):
        self.host, self.port, self.token, self.timeout = host, int(port), token, timeout

    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    def call(self, name, *args, **kwargs):
        body = json.dumps({"fn": name, "args": args, "kwargs": kwargs}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/rpc", data=body,
            headers={"Content-Type": "application/json; charset=utf-8", "X-Token": self.token},
        )
        try:
            with _OPENER.open(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            e.close()
            if e.code == 401:
                raise AuthError("รหัสเชื่อมต่อไม่ถูกต้อง กรุณาตรวจรหัสที่เครื่องหลัก") from None
            raise ServerUnavailable(f"เครื่องหลักตอบกลับผิดปกติ ({e.code})") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ServerUnavailable(
                f"เชื่อมต่อเครื่องหลัก ({self.host}) ไม่ได้ กรุณาตรวจว่าเครื่องหลักเปิดอยู่และอยู่ในวงแลนด์เดียวกัน"
            ) from e
        if "error" in data:
            raise _ERROR_TYPES.get(data.get("type"), RuntimeError)(data["error"])
        return data["ok"]

    def ping(self, timeout=1.5):
        try:
            with _OPENER.open(self.base_url + "/ping", timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8")).get("app") == APP_ID
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def check(self):
        """ทดสอบการเชื่อมต่อ+รหัส คืนค่า None ถ้าผ่าน หรือข้อความปัญหา"""
        if not self.ping(timeout=3):
            return f"หาเครื่องหลักที่ {self.host}:{self.port} ไม่เจอ (ตรวจ IP และไฟร์วอลล์ของเครื่องหลัก)"
        try:
            self.call("get_settings")
        except AuthError as e:
            return str(e)
        except Exception as e:
            return str(e)
        return None


def _broadcast_targets():
    targets = ["255.255.255.255"]
    for ip in local_ips():  # เครื่องที่มีหลายการ์ดเครือข่าย: ส่งไปทุกวงด้วย (สมมติวง /24)
        targets.append(ip.rsplit(".", 1)[0] + ".255")
    targets.append("127.0.0.1")  # เครื่องนี้เป็นเครื่องหลักเอง
    return list(dict.fromkeys(targets))


def discover(timeout=2.0, broadcast=None, port=netconfig.DISCOVERY_PORT):
    """ค้นหาเครื่องหลักในวงแลนด์ คืนรายการ [{'host','port','name'}] (ส่งคำถามซ้ำทุก 0.5 วินาที กันแพ็กเก็ตหาย)"""
    targets = [broadcast] if broadcast else _broadcast_targets()
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.1)
        start = time.time()
        last_sent = 0
        while time.time() - start < timeout:
            if time.time() - last_sent >= 0.5:
                for target in targets:
                    try:
                        sock.sendto(DISCOVER_MESSAGE, (target, port))
                    except OSError:
                        pass
                last_sent = time.time()
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                info = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if info.get("app") == APP_ID:
                found[addr[0]] = {"host": addr[0], "port": info.get("port", netconfig.DEFAULT_PORT), "name": info.get("name", "")}
    finally:
        sock.close()
    results = list(found.values())
    # เครื่องหลักตอบกลับมาทั้งทาง 127.0.0.1 และ IP จริง: เก็บเฉพาะ IP จริง (เครื่องอื่นเรียก 127.0.0.1 ไม่ได้)
    real = [r for r in results if not r["host"].startswith("127.")]
    return real or results


def local_ips():
    """IP ของเครื่องนี้ในวงแลนด์ (ไว้บอกให้เครื่องลูกกรอก)"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # ไม่ส่งข้อมูลจริง ใช้หา IP ที่ระบบเลือกออกวงแลนด์
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


def server_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--server"]
    return [sys.executable, f"{app_paths.project_dir()}/main.py", "--server"]


def ensure_server_running(port, wait=25):
    """เปิดเซิร์ฟเวอร์เบื้องหลังบนเครื่องนี้ถ้ายังไม่ทำงาน คืน True เมื่อพร้อมใช้งาน"""
    probe = RemoteClient("127.0.0.1", port, "")
    if probe.ping():
        return True
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_GROUP | NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(server_command(), **kwargs)
    deadline = time.time() + wait
    while time.time() < deadline:
        if probe.ping(timeout=1):
            return True
        time.sleep(0.5)
    return False


def stop_local_server(port, token):
    try:
        RemoteClient("127.0.0.1", port, token, timeout=3).call("__shutdown__")
    except Exception:
        pass
