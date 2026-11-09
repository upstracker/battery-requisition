"""ให้เซิร์ฟเวอร์เครื่องหลักเปิดเองทุกครั้งที่ล็อกอิน Windows (ไม่ต้องเปิดโปรแกรมออกใบเบิกค้างไว้)"""
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BatteryRequisitionServer"


def supported():
    return sys.platform.startswith("win") and getattr(sys, "frozen", False)


def enable():
    if not supported():
        return False
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --server')
    return True


def disable():
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
    return True
