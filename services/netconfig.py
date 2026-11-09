"""ตั้งค่าโหมดการใช้งาน: standalone (เครื่องเดียว) / server (เครื่องหลัก) / client (เครื่องลูก)"""
import json
import os
import secrets

import app_paths

DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766
MODES = ("standalone", "server", "client")


def config_path():
    return os.path.join(app_paths.user_data_dir(), "config.json")


def load():
    """คืน dict ตั้งค่า หรือ None ถ้ายังไม่เคยตั้ง (เปิดโปรแกรมครั้งแรก)"""
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    if cfg.get("mode") not in MODES:
        return None
    cfg.setdefault("port", DEFAULT_PORT)
    cfg.setdefault("host", "127.0.0.1")
    cfg.setdefault("token", "")
    return cfg


def save(cfg):
    os.makedirs(app_paths.user_data_dir(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def new_token():
    return f"{secrets.randbelow(10 ** 6):06d}"


def effective(cfg):
    """ยังไม่เคยตั้งค่า = ทำงานเครื่องเดียวเหมือนเวอร์ชันก่อน"""
    return cfg or {"mode": "standalone", "host": "127.0.0.1", "port": DEFAULT_PORT, "token": ""}
