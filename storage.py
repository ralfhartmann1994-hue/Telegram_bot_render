# storage.py
import json
import threading
import time
from pathlib import Path
from typing import Dict
import importlib

config = importlib.import_module("config") if Path("config.py").exists() else None
DB_PATH = Path(getattr(config, "USERS_DB_PATH", "users_db.json"))

_users_lock = threading.RLock()
users: Dict[int, dict] = {}

def load_users():
    global users
    try:
        if DB_PATH.exists():
            with DB_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            users = {int(k): v for k, v in data.items()}
        else:
            users = {}
    except Exception as e:
        print(f"[load_users ERROR] {e}")
        users = {}

def save_users():
    try:
        with _users_lock:
            tmp = DB_PATH.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in users.items()}, f, ensure_ascii=False, indent=2)
            tmp.replace(DB_PATH)
    except Exception as e:
        print(f"[save_users ERROR] {e}")

def ensure_user(uid: int):
    with _users_lock:
        if uid not in users or users[uid] is None:
            users[uid] = {
                "id": uid,
                "name": None,
                "age": None,
                "gender": None,
                "partner": None,
                "state": None,
                "respect": 100,
                "points": 100,
                "referrer": None,
                "referral_code": None,
                "history": [],
                "banned_full": False,
                "muted_until": None,
                "chat_started_at": None
            }
            save_users()
        return users[uid]

def update_user_dict(uid: int, updates: dict):
    with _users_lock:
        ensure_user(uid)
        users[uid].update(updates)
        save_users()

def append_history(uid: int, text: str):
    with _users_lock:
        u = ensure_user(uid)
        hist = u.get("history", [])
        hist.append({"ts": int(time.time()), "text": text})
        if len(hist) > 1000:
            hist = hist[-1000:]
        u["history"] = hist
        save_users()
