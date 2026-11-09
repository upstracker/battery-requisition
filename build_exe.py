"""
สคริปต์ช่วยแปลงโปรแกรมเป็นไฟล์ติดตั้ง .exe บน Windows
วิธีใช้:
    python build_exe.py
"""
import os
import sys
import subprocess
import shutil

def build():
    print("=" * 60)
    print("เริ่มกระบวนการสร้างไฟล์ .exe สำหรับ Windows PC")
    print("=" * 60)

    # ตรวจสอบ PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("กำลังติดตั้ง PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # รันคำสั่ง PyInstaller
    # แยก path separator ตามระบบปฏิบัติการ
    path_sep = ";" if sys.platform.startswith("win") else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--name=ระบบออกใบเบิก",
        f"--add-data=assets{path_sep}assets",
        "--collect-all=customtkinter",
        "--collect-all=fpdf2",
        "--collect-all=uharfbuzz",
        "--clean",
        "-y",
        "main.py"
    ]

    print("รันคำสั่ง PyInstaller:", " ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("✅ สร้างไฟล์โปรแกรมสำเร็จ!")
        print(f"โปรแกรมอยู่ที่โฟลเดอร์: dist/ระบบออกใบเบิก/")
        print("=" * 60)
        print("คำแนะนำสำหรับการแจกจ่าย:")
        print("1. สามารถบีบอัดโฟลเดอร์ 'dist/ระบบออกใบเบิก' เป็น .zip แล้วส่งให้เครื่องอื่นเปิดใช้งานได้ทันที")
        print("2. หรือใช้โปรแกรม Inno Setup เปิดไฟล์ 'installer_setup.iss' เพื่อคอมไพล์เป็นไฟล์ติดตั้ง Setup.exe")
    else:
        print("❌ เกิดข้อผิดพลาดในการสร้างไฟล์")

if __name__ == "__main__":
    build()
