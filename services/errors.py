class ConflictError(ValueError):
    """ใบเบิกถูกแก้ไขหรือยกเลิกโดยเครื่องอื่นระหว่างที่เปิดแก้อยู่"""


class ServerUnavailable(ConnectionError):
    """เชื่อมต่อเครื่องหลักไม่ได้"""


class AuthError(PermissionError):
    """รหัสเชื่อมต่อไม่ถูกต้อง"""
