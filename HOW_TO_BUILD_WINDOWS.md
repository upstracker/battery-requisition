# คู่มือการสร้างไฟล์ติดตั้ง Windows (Windows Installer Build Guide)

โปรแกรมถูกออกแบบและเตรียมไฟล์สำหรับสร้างตัวติดตั้งสำหรับ PC Windows ไว้อย่างสมบูรณ์ รองรับระบบปฏิบัติการ:
- **Windows 7 SP1 (32-bit & 64-bit)**
- **Windows 8 & 8.1**
- **Windows 10**
- **Windows 11**

---

## 🚀 วิธีที่ 1: สั่ง Build บนคลาวด์อัตโนมัติ (ไม่ต้องใช้เครื่อง Windows) *[แนะนำ]*

หากคุณทำงานบน Mac และไม่มีเครื่อง Windows ในตอนนี้ สามารถใช้ระบบ **GitHub Actions** ที่สร้างไว้ให้คอมไพล์เป็นไฟล์ติดตั้งบนคลาวด์ได้ฟรี:

1. นำโฟลเดอร์โปรเจกต์นี้ขึ้น GitHub Repository (เช่น `git push origin main`)
2. เข้าไปที่แท็บ **Actions** บน GitHub
3. เลือก Workflow **"Build Windows Installer (Win 7/8/10/11)"**
4. คลิกปุ่ม **"Run workflow"**
5. รอระบบทำงานประมาณ 2-3 นาที จะได้ไฟล์สำเร็จรูป 2 แบบให้ดาวน์โหลดในหัวข้อ **Artifacts**:
   - `Setup_BatteryRequisition_v1.0.0_Installer`: ไฟล์ติดตั้ง `.exe` (มีตัวช่วยติดตั้ง Next->Next->Finish และไอคอน Desktop)
   - `BatteryRequisition_Portable_v1.0.0_Zip`: ไฟล์ ZIP แบบพกพา แตกไฟล์แล้วเปิดใช้ได้ทันที

---

## 💻 วิธีที่ 2: สั่ง Build ใน 1 คลิก บนเครื่อง Windows (Local Build)

หากคุณมีเครื่องคอมพิวเตอร์ Windows หรือเครื่องเพื่อน:

### สิ่งที่ต้องมีในเครื่อง Windows:
1. **Python:** แนะนำ **Python 3.8.10** (เพื่อให้ใช้ได้กับ Windows 7/8/10/11 ทั้งหมด)
   - ดาวน์โหลด: https://www.python.org/downloads/release/python-3810/
   - *ข้อสำคัญ:* ตอนติดตั้ง ให้ติ๊กถูกหน้า **"Add Python to PATH"**
2. **Inno Setup (ฟรี):** สำหรับสร้างตัวติดตั้ง Setup.exe
   - ดาวน์โหลด: https://jrsoftware.org/isdl.php

### ขั้นตอนการสร้างไฟล์:
1. ก๊อปปี้โฟลเดอร์โปรเจกต์นี้ไปไว้ที่เครื่อง Windows
2. ดับเบิลคลิกที่ไฟล์ **`build_windows.bat`**
3. ระบบจะทำงานอัตโนมัติ:
   - ติดตั้ง Library ทั้งหมดให้เอง
   - คอมไพล์โปรแกรมผ่าน PyInstaller
   - เรียก Inno Setup สร้างไฟล์ตัวติดตั้ง
4. เมื่อเสร็จสิ้น จะได้ไฟล์ติดตั้งอยู่ที่:
   - **`dist_installer\Setup_BatteryRequisition_v1.0.0.exe`**

---

## 🛡️ ความปลอดภัยของข้อมูลเมื่อมีการติดตั้งเวอร์ชันใหม่ในอนาคต

- โปรแกรมที่ติดตั้งแล้วเก็บข้อมูลทั้งหมดไว้ที่ `%LOCALAPPDATA%\BatteryRequisition\` (ผู้ใช้ทั่วไปมีสิทธิ์เขียนเสมอ ไม่ต้องรันแบบ Administrator)
  - `data\inventory.db` ฐานข้อมูล, `output_pdfs\` ไฟล์ PDF, `database_backups\` ไฟล์สำรอง, `exported_reports\` รายงาน Excel
- ครั้งแรกที่เปิดเวอร์ชันนี้ ถ้ามีฐานข้อมูลเดิมที่ `{โฟลเดอร์โปรแกรม}\data\inventory.db` โปรแกรมจะคัดลอกย้ายมาให้อัตโนมัติ
- ถ้าเครื่องยังไม่มีข้อมูลเลย โปรแกรมจะนำเข้ารุ่นแบตเตอรี่จากไฟล์ `รุ่นแบตเตอรี่.xlsx` ที่มากับโปรแกรมให้เอง
- ติดตั้งเวอร์ชันใหม่ทับ หรือถอนการติดตั้ง จะไม่ลบข้อมูลใน `%LOCALAPPDATA%\BatteryRequisition\`
