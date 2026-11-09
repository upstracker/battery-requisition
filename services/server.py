"""
เซิร์ฟเวอร์วงแลนด์ของเครื่องหลัก: รับคำสั่งจากเครื่องลูกผ่าน HTTP (JSON) แล้วเรียก inventory_service
เฉพาะบนเครื่องนี้ ฐานข้อมูล SQLite จึงถูกเปิดโดยเครื่องหลักเครื่องเดียว (ปลอดภัยกว่าแชร์ไฟล์ข้ามเครื่อง)
"""
import hmac
import json
import os
import socket
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import app_paths
from services import inventory_service, netconfig
from services.rpc_api import RPC_FUNCTIONS

MAX_BODY = 8 * 1024 * 1024
APP_ID = "battery-requisition"
DISCOVER_MESSAGE = b"BATREQ_DISCOVER"


def log(message):
    try:
        path = os.path.join(app_paths.user_data_dir(), "server.log")
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
    except OSError:
        pass


class RpcServer(ThreadingHTTPServer):
    daemon_threads = True
    # บน Windows SO_REUSEADDR ทำให้เปิดซ้อนพอร์ตเดียวกันได้ ปิดไว้เพื่อให้เปิดเซิร์ฟเวอร์ซ้ำไม่ได้
    allow_reuse_address = not sys.platform.startswith("win")

    def __init__(self, address, token):
        super().__init__(address, RpcHandler)
        self.token = token


class RpcHandler(BaseHTTPRequestHandler):
    server_version = "BatteryRequisition/1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ping":
            self._send(200, {"ok": "pong", "app": APP_ID})
        else:
            self._send(404, {"error": "not found", "type": "NotFound"})

    def do_POST(self):
        if self.path != "/rpc":
            self._send(404, {"error": "not found", "type": "NotFound"})
            return
        supplied = self.headers.get("X-Token", "")
        if not self.server.token or not hmac.compare_digest(supplied, self.server.token):
            self._send(401, {"error": "รหัสเชื่อมต่อไม่ถูกต้อง", "type": "AuthError"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("ขนาดคำขอไม่ถูกต้อง")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            name = request.get("fn")
            args = request.get("args") or []
            kwargs = request.get("kwargs") or {}
            if name == "__shutdown__":
                self._send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if name not in RPC_FUNCTIONS:
                raise ValueError(f"ไม่รู้จักคำสั่ง {name}")
            result = getattr(inventory_service, name)(*args, **kwargs)
            self._send(200, {"ok": result})
        except ValueError as e:
            self._send(200, {"error": str(e), "type": type(e).__name__})
        except Exception as e:  # ข้อผิดพลาดที่ไม่คาดคิด: บันทึกไว้ที่เครื่องหลัก ส่งข้อความสั้นกลับไป
            log(f"ERROR {self.path} {type(e).__name__}: {e}")
            self._send(200, {"error": f"เครื่องหลักเกิดข้อผิดพลาด: {e}", "type": "ServerError"})


def _discovery_loop(rpc_port, discovery_port, stop):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", discovery_port))
    except OSError as e:
        log(f"discovery disabled: {e}")
        sock.close()
        return
    sock.settimeout(1.0)
    reply = json.dumps({"app": APP_ID, "port": rpc_port, "name": socket.gethostname()}).encode("utf-8")
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(256)
        except socket.timeout:
            continue
        except OSError:
            break
        if data.strip() == DISCOVER_MESSAGE:
            try:
                sock.sendto(reply, addr)
            except OSError:
                pass
    sock.close()


def _backup_loop(stop):
    from database.db import daily_auto_backup
    while not stop.wait(3600):
        try:
            daily_auto_backup()
        except Exception as e:
            log(f"backup error: {e}")


def start_server(port, token, bind_host="", discovery_port=netconfig.DISCOVERY_PORT, background_jobs=True):
    """เริ่มเซิร์ฟเวอร์ คืนค่า (server, stop_event) ผู้เรียกต้องรัน server.serve_forever() เอง"""
    server = RpcServer((bind_host, port), token)
    stop = threading.Event()
    if discovery_port:
        threading.Thread(target=_discovery_loop, args=(server.server_address[1], discovery_port, stop), daemon=True).start()
    if background_jobs:
        threading.Thread(target=_backup_loop, args=(stop,), daemon=True).start()
    return server, stop


def run_forever():
    """จุดเริ่มของโหมด `--server` (ไม่มีหน้าต่าง)"""
    from database.db import init_db

    cfg = netconfig.load()
    if not cfg or cfg.get("mode") != "server":
        log("ไม่ได้ตั้งเป็นเครื่องหลัก ไม่เริ่มเซิร์ฟเวอร์")
        return 1
    init_db()
    try:
        server, stop = start_server(cfg["port"], cfg["token"])
    except OSError as e:
        log(f"เริ่มเซิร์ฟเวอร์ไม่ได้ (อาจเปิดอยู่แล้ว): {e}")
        return 1
    log(f"เริ่มเซิร์ฟเวอร์ที่พอร์ต {cfg['port']}")
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        log("หยุดเซิร์ฟเวอร์")
    return 0
