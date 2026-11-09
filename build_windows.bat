@echo off
chcp 65001 > nul
cls
echo =====================================================================
echo   ชุดสคริปต์คอมไพล์โปรแกรมออกใบเบิกแบตเตอรี่ สำหรับ Windows (1-Click)
echo   รองรับ Windows 7 SP1, Windows 8, 8.1, 10, และ 11
echo =====================================================================
echo.

:: 1. ตรวจสอบการติดตั้ง Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] ไม่พบการติดตั้ง Python ในเครื่องนี้
    echo กรุณาติดตั้ง Python 3.8.10 หรือเวอร์ชันที่ต้องการ และติ๊ก "Add Python to PATH"
    pause
    exit /b 1
)

echo [*] 1. ติดตั้งไลบรารีที่จำเป็น (Dependencies)...
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] ไม่สามารถติดตั้งไลบรารีได้สำเร็จ
    pause
    exit /b 1
)

echo.
echo [*] 2. เริ่มคอมไพล์โปรแกรมด้วย PyInstaller (Standalone EXE)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller app.spec --clean -y
if %errorlevel% neq 0 (
    echo [ERROR] เกิดข้อผิดพลาดในการคอมไพล์ PyInstaller
    pause
    exit /b 1
)

echo.
echo [+] คอมไพล์โปรแกรมสำเร็จ! โฟลเดอร์โปรแกรมอยู่ที่: dist\BatteryRequisition\
echo.

:: 3. ค้นหา Inno Setup เพื่อสร้างไฟล์ติดตั้ง Setup.exe
echo [*] 3. กำลังค้นหาโปรแกรม Inno Setup Compiler (ISCC.exe)...
set ISCC="none"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 5\ISCC.exe"

if %ISCC%=="none" (
    echo [NOTE] ไม่พบ Inno Setup บนเครื่องนี้
    echo สามารถใช้งานโปรแกรมแบบพกพาได้ทันทีจากโฟลเดอร์: dist\BatteryRequisition\
    echo หากต้องการสร้างไฟล์ติดตั้ง Setup.exe กรุณาดาวน์โหลด Inno Setup ฟรีที่:
    echo https://jrsoftware.org/isdl.php
) else (
    echo [+] พบ Inno Setup: %ISCC%
    echo [*] กำลังสร้างไฟล์ติดตั้ง Setup_BatteryRequisition_v1.0.0.exe...
    %ISCC% installer.iss
    if %errorlevel% equ 0 (
        echo.
        echo =====================================================================
        echo   [SUCCESS] สร้างไฟล์ติดตั้งสำเร็จเรียบร้อยแล้ว!
        echo   ไฟล์ติดตั้งอยู่ที่: dist_installer\Setup_BatteryRequisition_v1.0.0.exe
        echo =====================================================================
    ) else (
        echo [ERROR] ไม่สามารถสร้างไฟล์ติดตั้งด้วย Inno Setup ได้
    )
)

echo.
pause
