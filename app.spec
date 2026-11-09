# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# รวบรวมไฟล์ Asset และธีมของ CustomTkinter
ctk_datas = collect_data_files('customtkinter')

added_datas = [
    ('assets', 'assets'),
    ('รุ่นแบตเตอรี่.xlsx', '.'),
] + ctk_datas

hidden_imports = [
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'customtkinter',
    'fpdf',
    'openpyxl',
    'sqlite3',
    'services',
    'database',
    'ui',
] + collect_submodules('customtkinter')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'numpy', 'IPython', 'notebook', 'tkinter.test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BatteryRequisition',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/car_battery.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BatteryRequisition',
)
