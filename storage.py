import json
import threading
import time
from pathlib import Path
from typing import Dict
import importlib

# استيراد التكوين
config = importlib.import_module("config") if Path("config.py").exists() else None
DB_PATH = Path(getattr(config, "USERS_DB_PATH", "users_db.json"))

# قفل للوصول إلى البيانات من قبل عدة خيوط
_users_lock = threading.RLock()
users: Dict[int, dict] = {}

# تحميل بيانات المستخدمين من ملف JSON
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

# حفظ بيانات المستخدمين في ملف JSON
def save_users():
    try:
        with _users_lock:
            tmp = DB_PATH.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in users.items()}, f, ensure_ascii=False, indent=2)
            tmp.replace(DB_PATH)
    except Exception as e:
        print(f"[save_users ERROR] {e}")

# التأكد من وجود المستخدم أو إضافته إذا لم يكن موجودًا
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

# تحديث بيانات المستخدم
def update_user_dict(uid: int, updates: dict):
    with _users_lock:
        ensure_user(uid)
        users[uid].update(updates)
        save_users()

# إضافة نص إلى سجل المحادثات الخاصة بالمستخدم
def append_history(uid: int, text: str):
    with _users_lock:
        u = ensure_user(uid)
        hist = u.get("history", [])
        hist.append({"ts": int(time.time()), "text": text})
        if len(hist) > 1000:
            hist = hist[-1000:]
        u["history"] = hist
        save_users()

# دالة لتحميل بيانات المستخدم
def get_user(uid: int):
    with _users_lock:
        ensure_user(uid)
        return users.get(uid)

# دالة لحفظ الاسم بعد التحقق من صلاحيته
def set_name(user_id, name):
    if len(name) < 2 or len(name) > 30:
        raise ValueError("الاسم يجب أن يكون بين 2 و 30 حرفًا.")
    users.setdefault(user_id, {})["name"] = name
    save_users()

# دالة لحفظ الجنس بعد التحقق من صلاحيته
def set_gender(user_id, gender):
    valid_genders = ["ذكر", "أنثى"]
    if gender not in valid_genders:
        raise ValueError("الجنس يجب أن يكون إما 'ذكر' أو 'أنثى'.")
    users.setdefault(user_id, {})["gender"] = gender
    save_users()

# دالة لحفظ العمر بعد التحقق من صلاحيته
def set_age(user_id, age):
    if age < 10 or age > 120:
        raise ValueError("العمر يجب أن يكون بين 10 و 120 عامًا.")
    users.setdefault(user_id, {})["age"] = age
    save_users()

# دالة لاسترجاع البيانات من الملف
def get_name(user_id):
    return users.get(user_id, {}).get("name")

def get_gender(user_id):
    return users.get(user_id, {}).get("gender")

def get_age(user_id):
    return users.get(user_id, {}).get("age")

# دالة لاسترجاع بيانات الملف الشخصي
def profile_text(u: dict):
    name = u.get("name") or "غير محدد"
    age = u.get("age") or "غير محدد"
    gender = u.get("gender") or "غير محدد"
    respect = u.get("respect", "--")
    return f"👤 <b>ملفي الشخصي</b>\n• الاسم: {name}\n• العمر: {age}\n• الجنس: {gender}\n• الاحترام: ⭐ {respect}"

# بدء جلسة المحادثة وحفظ البيانات
def start_history(u: dict):
    u.setdefault("history", [])

# إنهاء الجلسة (محادثة) وحفظ البيانات
def end_session(u1: dict, u2: dict=None):
    try:
        if u1:
            u1["partner"] = None
            u1["chat_started_at"] = None
        if u2:
            u2["partner"] = None
            u2["chat_started_at"] = None
        save_users()
    except Exception:
        pass 
