# Profile_manger.py
from storage import ensure_user, update_user_dict, append_history
import re

NAME_RE = re.compile(r"^[\p{L}\w\s\-]{2,30}$", re.UNICODE) if False else re.compile(r"^[\w\s\-]{2,30}$")

def ensure_user(uid: int):
    return ensure_user(uid)

def set_name(user_id, name):
    storage.USERS.setdefault(user_id, {})
    storage.USERS[user_id]["name"] = name

def get_name(user_id):
    return storage.USERS.get(user_id, {}).get("name")

def set_gender(user_id, gender):
    storage.USERS.setdefault(user_id, {})
    storage.USERS[user_id]["gender"] = gender

def get_gender(user_id):
    return storage.USERS.get(user_id, {}).get("gender")

def set_age(user_id, age):
    storage.USERS.setdefault(user_id, {})
    storage.USERS[user_id]["age"] = age

def get_age(user_id):
    return storage.USERS.get(user_id, {}).get("age")

def profile_text(u: dict):
    name = u.get("name") or "غير محدد"
    age = u.get("age") or "غير محدد"
    gender = u.get("gender") or "غير محدد"
    respect = u.get("respect", "--")
    return f"👤 <b>ملفي الشخصي</b>\n• الاسم: {name}\n• العمر: {age}\n• الجنس: {gender}\n• الاحترام: ⭐ {respect}"

def start_history(u: dict):
    # مجرد علامة، يمكن توسيعها
    u.setdefault("history", [])
    return

def end_session(u1: dict, u2: dict=None):
    # مسح تاريخ الجلسة أو إنهاء الشراكة
    try:
        if u1:
            u1["partner"] = None
            u1["chat_started_at"] = None
        if u2:
            u2["partner"] = None
            u2["chat_started_at"] = None
    except Exception:
        pass 
