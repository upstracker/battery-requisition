; =====================================================================
; Inno Setup Script: ระบบออกใบเบิกจ่ายแบตเตอรี่ขึ้นรถส่งของ (A5 Landscape)
; รองรับระบบปฏิบัติการ Windows 7 SP1, Windows 8, 8.1, 10 และ 11
; =====================================================================

#define MyAppName "ระบบออกใบเบิกจ่ายแบตเตอรี่ขึ้นรถส่งของ"
#define MyAppVersion "1.0.0"
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
OutputBaseFilename=Setup_BatteryRequisition_v1.0.0
SetupIconFile=assets\car_battery.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; บีบอัดไฟล์ตัวติดตั้งสูงสุดแบบ LZMA2
Compression=lzma2/ultra64
SolidCompression=yes

; กำหนดความเข้ากันได้ย้อนหลัง: รองรับตั้งแต่ Windows 7 SP1 ขึ้นไป (Kernel 6.1sp1)
MinVersion=6.1sp1

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

; ฐานข้อมูลที่ใช้งานจริงอยู่ที่ %LOCALAPPDATA%\BatteryRequisition\data (โปรแกรมสร้างเองตอนเปิดครั้งแรก)
; ถ้ามีโฟลเดอร์ data ตอน build จะถูกคัดลอกไปเป็นข้อมูลตั้งต้น และโปรแกรมจะย้ายไป %LOCALAPPDATA% ให้ครั้งแรก
Source: "data\*"; DestDir: "{app}\data"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\ระบบออกใบเบิกแบตเตอรี่\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\ระบบออกใบเบิกแบตเตอรี่\ถอนการติดตั้งโปรแกรม (Uninstall)"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "เปิดใช้งานโปรแกรมทันที (Launch Application)"; Flags: nowait postinstall skipifsilent
