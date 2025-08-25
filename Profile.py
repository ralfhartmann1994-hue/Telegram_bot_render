# profile.py
import re, time
from typing import Optional
from storage import users, save_users

def sanitize_name(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not (2 <= len(s) <= 30):
        return None
    if not re.fullmatch(r"[A-Za-z\u0621-\u064A\u0660-\u0669\u0670-\u0671\s'\-]+", s):
        return None
    if any(ch.isdigit() for ch in s):
        return None
    return s

def sanitize_age(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s.isdigit():
        return None
    age = int(s)
    if 10 <= age <= 120:
        return age
    return None

def profile_text(u) -> str:
    name = u.get("name") or "غير محدد"
    age = u.get("age") or "غير محدد"
    gender = u.get("gender") or "غير محدد"
    respect = u.get("respect", 80)
    return (
        f"👤 <b>ملفك</b>\n"
        f"• الاسم: {name}\n"
        f"• العمر: {age}\n"
        f"• الجنس: {gender} (ثابت)\n"
        f"• الاحترام: ⭐ {respect}"
    )

def start_history(u):
    u["history"] = []
    u["chat_started_at"] = int(time.time())
    save_users()

def append_history(u1, u2, from_id: int, text: str):
    rec = {"ts": int(time.time()), "from": from_id, "text": text}
    for u in (u1, u2):
        h = u.get("history") or []
        h.append(rec)
        if len(h) > 50:
            del h[:-50]
        u["history"] = h
    save_users()

def end_session(u1, u2):
    # نقل آخر 50 رسالة إلى last_history وفصل
    if u1:
        u1["last_history"] = (u1.get("history") or [])[-50:]
        u1["history"] = []
        u1["partner"] = None
        u1["chat_started_at"] = None
    if u2:
        u2["last_history"] = (u2.get("history") or [])[-50:]
        u2["history"] = []
        u2["partner"] = None
