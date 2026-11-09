; =====================================================================
; Inno Setup Script: ระบบออกใบเบิกจ่ายแบตเตอรี่ขึ้นรถส่งของ (A5 Landscape)
; รองรับระบบปฏิบัติการ Windows 10 และ 11
; =====================================================================

#define MyAppName "ระบบออกใบเบิกจ่ายแบตเตอรี่ขึ้นรถส่งของ"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "คลังแบตเตอรี่และบริการ"
#define MyAppExeName "BatteryRequisition.exe"
#define MyAppAssocName "Battery Requisition Slip"

[Setup]
; App Identity
AppId={{D37B4C8A-692B-4A19-952F-9C1D9F128E61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\BatteryRequisitionApp
DefaultGroupName=ระบบออกใบเบิกแบตเตอรี่
AllowNoIcons=yes
OutputDir=dist_installer
OutputBaseFilename=Setup_BatteryRequisition_v1.1.0
SetupIconFile=assets\car_battery.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; บีบอัดไฟล์ตัวติดตั้งสูงสุดแบบ LZMA2
Compression=lzma2/ultra64
SolidCompression=yes

; รองรับ Windows 10 และ 11 (Python 3.12 ไม่รองรับ Windows 7/8)
MinVersion=10.0

; สิทธิ์ในการติดตั้ง
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; หน้าต่างแสดงผล
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "สร้างไอคอนบนหน้าจอ Desktop (Create desktop shortcut)"; GroupDescription: "ตัวเลือกเพิ่มเติม:"

[Files]
; คัดลอกไฟล์โปรแกรมทั้งหมดจากโฟลเดอร์ dist\BatteryRequisition
Source: "dist\BatteryRequisition\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ข้อมูลของผู้ใช้ (ฐานข้อมูล PDF ไฟล์สำรอง) อยู่ที่ %LOCALAPPDATA%\BatteryRequisition\ โปรแกรมสร้างเองตอนเปิดครั้งแรก
; ตัวติดตั้งและตัวถอนการติดตั้งจะไม่แตะต้องโฟลเดอร์นั้น

[Icons]
Name: "{autoprograms}\ระบบออกใบเบิกแบตเตอรี่\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\ระบบออกใบเบิกแบตเตอรี่\ถอนการติดตั้งโปรแกรม (Uninstall)"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "เปิดใช้งานโปรแกรมทันที (Launch Application)"; Flags: nowait postinstall skipifsilent
