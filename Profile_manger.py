
# =================
# Profile_manger.py (مصحح)
# =================
import storage
from storage import ensure_user as ensure_user_storage, update_user_dict, append_history, save_users
import re

# Regex للأسماء (يمكن تعديل Unicode لاحقًا)
NAME_RE = re.compile(r"^[\w\s\-]{2,30}$")

def ensure_user(uid: int):
    return ensure_user_storage(uid)

def set_name(user_id, name):
    storage.users.setdefault(user_id, {})
    storage.users[user_id]["name"] = name
    save_users()  # حفظ البيانات فوراً

def get_name(user_id):
    return storage.users.get(user_id, {}).get("name")

def set_gender(user_id, gender):
    storage.users.setdefault(user_id, {})
    storage.users[user_id]["gender"] = gender
    save_users()  # حفظ البيانات فوراً

def get_gender(user_id):
    return storage.users.get(user_id, {}).get("gender")

def set_age(user_id, age):
    storage.users.setdefault(user_id, {})
    storage.users[user_id]["age"] = age
    save_users()  # حفظ البيانات فوراً

def get_age(user_id):
    return storage.users.get(user_id, {}).get("age")

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
        save_users()
    except Exception:
        pass
