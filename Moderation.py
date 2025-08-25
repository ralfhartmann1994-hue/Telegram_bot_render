# moderation.py
import time
from typing import Tuple
from config import PENALTY_PER_HIT, WARN_THRESHOLD, BAN_THRESHOLD, PARTIAL_BAN_DAYS
from storage import users, save_users
from bad_words import count_bad_words

def is_muted(u) -> Tuple[bool, int | None]:
    mu = u.get("mute_until")
    if not mu:
        return (False, None)
    now = time.time()
    if now >= mu:
        u["mute_until"] = None
        save_users()
        return (False, None)
    return (True, int(mu - now))

def apply_respect(uid: int, text: str) -> str | None:
    """تطبيق الخصم عند إرسال رسالة تحتوي إساءة، مع تصعيد المراحل."""
    u = users.get(uid)
    if not u or u.get("banned_full"):
        return None
    bad = count_bad_words(text)
    if bad <= 0:
        return None

    stage = u.get("penalty_stage", 1)
    threshold = 3 if stage == 1 else (2 if stage == 2 else 1)
    penalties = bad // threshold
    if penalties <= 0:
        return None

    deduct = PENALTY_PER_HIT * penalties
    u["respect"] = max(0, u.get("respect", 80) - deduct)
    u["total_penalties"] = int(u.get("total_penalties", 0)) + penalties

    # تصعيد
    tp = u["total_penalties"]
    if stage == 1 and tp >= 1:
        u["penalty_stage"] = 2
    elif stage == 2 and tp >= 2:
        u["penalty_stage"] = 3

    msg = None
    if u["respect"] <= BAN_THRESHOLD:
        u["banned_full"] = True
        msg = "🚫 تم حظرك نهائيًا بسبب تكرار الإساءة."
    elif u["respect"] <= WARN_THRESHOLD and not u.get("mute_until"):
        u["mute_until"] = time.time() + PARTIAL_BAN_DAYS * 24 * 3600
        msg = f"⏳ تم تفعيل حظر جزئي لمدة {PARTIAL_BAN_DAYS} أيام."

    save_users()
    return msg

def review_history_and_penalize(u1_id: int, u2_id: int, history: list) -> tuple[str, str]:
    """تحليل آخر 50 رسالة وخصم نقاط وفق الإساءة لكل طرف."""
    c1 = c2 = 0
    for r in history[-50:]:
        hits = count_bad_words(r.get("text", ""))
        if hits > 0:
            if r.get("from") == u1_id:
                c1 += hits
            elif r.get("from") == u2_id:
                c2 += hits

    d1 = d2 = 0
    if c1:
        d1 = c1 * PENALTY_PER_HIT
        users[u1_id]["respect"] = max(0, users[u1_id].get("respect", 80) - d1)
    if c2:
        d2 = c2 * PENALTY_PER_HIT
        users[u2_id]["respect"] = max(0, users[u2_id].get("respect", 80) - d2)
    save_users()

    return (
        f"أنت: -{d1} (اكتُشفت {c1} إساءات)",
        f"الطرف الآخر: -{d2} (اكتُشفت {c2} إساءات)"
    ) 
