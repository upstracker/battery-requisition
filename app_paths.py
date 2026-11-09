"""
ตำแหน่งไฟล์ทั้งหมดของโปรแกรม (ไม่ขึ้นกับโฟลเดอร์ที่เปิดโปรแกรม)

- resource_dir(): ไฟล์ที่มากับโปรแกรม อ่านอย่างเดียว (ฟอนต์, ไอคอน, รุ่นแบตเตอรี่.xlsx)
- user_data_dir(): ไฟล์ที่โปรแกรมเขียน (ฐานข้อมูล, PDF, backup, รายงาน Excel)
    * รันจากซอร์สโค้ด  -> โฟลเดอร์โปรเจกต์ (เหมือนเดิม)
    * รันจาก .exe       -> %LOCALAPPDATA%\\BatteryRequisition (ผู้ใช้มีสิทธิ์เขียนเสมอ)
    * ตั้งค่า BATTERY_REQ_HOME เพื่อบังคับตำแหน่ง (ใช้ในชุดทดสอบ)
"""
import os
import sys

APP_NAME = "BatteryRequisition"
HOME_ENV = "BATTERY_REQ_HOME"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def project_dir():
    return os.path.dirname(os.path.abspath(__file__))


def executable_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def resource_dir():
    if is_frozen():
        return getattr(sys, "_MEIPASS", executable_dir())
    return project_dir()


def user_data_dir():
    override = os.environ.get(HOME_ENV)
    if override:
        return os.path.abspath(override)
    if not is_frozen():
        return project_dir()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_NAME)


def _user_subdir(name):
    path = os.path.join(user_data_dir(), name)
    os.makedirs(path, exist_ok=True)
    return path


def data_dir():
    return _user_subdir("data")


def db_file():
    return os.path.join(data_dir(), "inventory.db")


def pdf_dir():
    return _user_subdir("output_pdfs")


def backup_dir():
    return _user_subdir("database_backups")


def reports_dir():
    return _user_subdir("exported_reports")


def font_file(name):
    return os.path.join(resource_dir(), "assets", "fonts", name)


def asset_file(name):
    return os.path.join(resource_dir(), "assets", name)


def battery_excel_file():
    return os.path.join(resource_dir(), "รุ่นแบตเตอรี่.xlsx")


def legacy_db_candidates():
    """ฐานข้อมูลเดิมที่อาจมีอยู่ก่อนย้ายตำแหน่ง เรียงตามลำดับที่ควรใช้"""
    if is_frozen():
        exe = executable_dir()
        return [
            os.path.join(exe, "data", "inventory.db"),
            os.path.join(resource_dir(), "data", "inventory.db"),
        ]
    return [os.path.join(project_dir(), "inventory.db")]
