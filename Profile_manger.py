# Profile_manger.py
import storage
from storage import ensure_user as ensure_user_storage, update_user_dict, append_history
import re

# Regex للأسماء (يمكن تعديل Unicode لاحقًا)
NAME_RE = re.compile(r"^[\w\s\-]{2,30}$")

def ensure_user(uid: int):
    return ensure_user_storage(uid)

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
    u.setdefault("history", [])

def end_session(u1: dict, u2: dict=None):
    try:
        if u1:
            u1["partner"] = None
            u1["chat_started_at"] = None
        if u2:
            u2["partner"] = None
            u2["chat_started_at"] = None
    except Exception:
        pass
