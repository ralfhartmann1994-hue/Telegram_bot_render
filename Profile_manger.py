import re
import time
from typing import Optional
from storage import users, save_users


# ========================
# 🟢 التحقق من البيانات
# ========================

def sanitize_name(s: str) -> Optional[str]:
    """التحقق من صحة الاسم (حروف عربية/لاتينية فقط، بدون أرقام)"""
    s = (s or "").strip()
    if not (2 <= len(s) <= 30):
        return None
    if not re.fullmatch(r"[A-Za-z\u0621-\u064A\u0660-\u0669\u0670-\u0671\s'\-]+", s):
        return None
    if any(ch.isdigit() for ch in s):
        return None
    return s


def sanitize_age(s: str) -> Optional[int]:
    """التحقق من العمر (10 - 120)"""
    s = (s or "").strip()
    if not s.isdigit():
        return None
    age = int(s)
    if 10 <= age <= 120:
        return age
    return None


def sanitize_gender(s: str) -> Optional[str]:
    """التحقق من الجنس (ذكر / أنثى)"""
    s = (s or "").strip().lower()
    if s in ["ذكر", "male", "m"]:
        return "ذكر"
    if s in ["أنثى", "انثى", "female", "f"]:
        return "أنثى"
    return None


# ========================
# 🟢 إدارة المستخدم
# ========================

def ensure_user(user_id: int):
    """إنشاء سجل للمستخدم إذا لم يكن موجود"""
    if user_id not in users:
        users[user_id] = {
            "id": user_id,
            "name": None,
            "age": None,
            "gender": None,
            "respect": 80,
            "history": [],
            "partner": None,
            "last_history": [],
            "chat_started_at": None,
        }
    return users[user_id]


def set_user_name(user_id: int, name: str) -> bool:
    """تعيين اسم المستخدم بعد التحقق"""
    try:
        clean_name = sanitize_name(name)
        if not clean_name:
            return False
        u = ensure_user(user_id)
        u["name"] = clean_name
        save_users()
        print(f"[PROFILE] Name updated: {user_id} -> {clean_name}")
        return True
    except Exception as e:
        print(f"[ERROR set_user_name] user={user_id}, err={e}")
        return False


def set_user_age(user_id: int, age_str: str) -> bool:
    """تعيين عمر المستخدم بعد التحقق"""
    try:
        age = sanitize_age(age_str)
        if not age:
            return False
        u = ensure_user(user_id)
        u["age"] = age
        save_users()
        print(f"[PROFILE] Age updated: {user_id} -> {age}")
        return True
    except Exception as e:
        print(f"[ERROR set_user_age] user={user_id}, err={e}")
        return False


def set_user_gender(user_id: int, gender_str: str) -> bool:
    """تعيين جنس المستخدم بعد التحقق"""
    try:
        gender = sanitize_gender(gender_str)
        if not gender:
            return False
        u = ensure_user(user_id)
        u["gender"] = gender
        save_users()
        print(f"[PROFILE] Gender updated: {user_id} -> {gender}")
        return True
    except Exception as e:
        print(f"[ERROR set_user_gender] user={user_id}, err={e}")
        return False


# ========================
# 🟢 الملف الشخصي
# ========================

def profile_text(u) -> str:
    """إظهار الملف الشخصي للمستخدم"""
    name = u.get("name") or "غير محدد"
    age = u.get("age") or "غير محدد"
    gender = u.get("gender") or "غير محدد"
    respect = u.get("respect", 80)
    return (
        f"👤 <b>ملفك</b>\n"
        f"• الاسم: {name}\n"
        f"• العمر: {age}\n"
        f"• الجنس: {gender}\n"
        f"• الاحترام: ⭐ {respect}"
    )


# ========================
# 🟢 إدارة الجلسات
# ========================

def start_history(u):
    """بدء جلسة محادثة جديدة"""
    u["history"] = []
    u["chat_started_at"] = int(time.time())
    save_users()


def append_history(sender_uid: int, text: str):
    """تسجيل رسالة جديدة في السجل"""
    u = users.get(sender_uid)
    if not u:
        return
    partner_id = u.get("partner")
    rec = {"ts": int(time.time()), "from": sender_uid, "text": text}
    # أضف للمرسل
    h = u.get("history", [])
    h.append(rec)
    u["history"] = h[-50:]
    # أضف للشريك إذا موجود
    if partner_id and partner_id in users:
        p = users[partner_id]
        ph = p.get("history", [])
        ph.append(rec)
        p["history"] = ph[-50:]
    save_users()


def end_session(u1, u2):
    """إنهاء جلسة المحادثة ونقل آخر 50 رسالة"""
    if u1:
        u1["last_history"] = (u1.get("history") or [])[-50:]
        u1["history"] = []
        u1["partner"] = None
        u1["chat_started_at"] = None
    if u2:
        u2["last_history"] = (u2.get("history") or [])[-50:]
        u2["history"] = []
        u2["partner"] = None
    save_users()
