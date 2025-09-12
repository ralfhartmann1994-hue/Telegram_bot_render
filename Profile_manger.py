# Profile_manger.py
from storage import ensure_user, update_user_dict, append_history
import re

NAME_RE = re.compile(r"^[\p{L}\w\s\-]{2,30}$", re.UNICODE) if False else re.compile(r"^[\w\s\-]{2,30}$")

def ensure_user(uid: int):
    return ensure_user(uid)

def set_user_name(uid: int, name: str):
    name = (name or "").strip()
    # بسيط: قبول حروف وأرقام ومسافات بين 2 و30
    if not (2 <= len(name) <= 30):
        return False
    update_user_dict(uid, {"name": name})
    return True

def set_user_age(uid: int, age_txt: str):
    try:
        age = int(age_txt)
        if age < 10 or age > 120:
            return False
        update_user_dict(uid, {"age": age})
        return True
    except Exception:
        return False

def set_user_gender(uid: int, gender: str):
    gender = (gender or "").strip()
    from config import GENDERS
    if gender not in GENDERS:
        return False
    update_user_dict(uid, {"gender": gender})
    return True

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
