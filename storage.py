# storage.py
import json, time, os
from typing import Dict, Any

DATA_FILE = "users.json"
users: Dict[int, Dict[str, Any]] = {}

def load_users():
    global users
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        users = {int(k): v for k, v in raw.items()}
    except FileNotFoundError:
        users = {}
    except Exception as e:
        print(f"[LOAD] {e}")
        users = {}

def save_users():
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        print(f"[SAVE] {e}")

def ensure_user(uid: int):
    if uid not in users:
        users[uid] = {
            "name": None,
            "age": None,
            "gender": None,        # يُضبط مرة واحدة
            "respect": 80,
            "penalty_stage": 1,    # 1 → 2 → 3
            "total_penalties": 0,
            "partner": None,
            "topic": None,
            "search_pref": None,   # تفضيل جنس الطرف الآخر في البحث الحالي
            "search_since": None,  # وقت بدء البحث الحالي
            "history": [],         # رسائل الجلسة الحالية (حد 50)
            "last_history": [],    # آخر محادثة منتهية
            "chat_started_at": None,
            "state": None,         # AWAIT_GENDER/NAME/AGE/… إلخ
            "banned_full": False,
            "mute_until": None,    # حظر جزئي حتى وقت محدد
            "created_at": time.time(),
        }
        save_users()
