

# =================
# Moderation.py (محسن)
# =================
import time
from typing import List
from storage import ensure_user, update_user_dict
from config import RESPECT_PENALTY_PER_BADWORD, PARTIAL_BAN_THRESHOLD, FULL_BAN_THRESHOLD, PARTIAL_BAN_DAYS, MAX_HISTORY_TO_REVIEW
from bad_words import BAD_WORDS, count_bad_words

def contains_bad_word(text: str) -> List[str]:
    if not text:
        return []
    t = text.lower()
    found = []
    for w in BAD_WORDS:
        if w in t:
            found.append(w)
    return found

def censor_text(text: str) -> str:
    t = text
    for w in BAD_WORDS:
        if w in t.lower():
            # استبدال مع الحفاظ على طول الكلمة
            stars = "*" * len(w)
            # استبدال بغض النظر عن حالة الأحرف
            import re
            t = re.sub(re.escape(w), stars, t, flags=re.IGNORECASE)
    return t

def is_muted(uid: int) -> bool:
    """تحقق إذا كان المستخدم مكتوم الصوت"""
    try:
        u = ensure_user(uid)
        muted_until = u.get("muted_until")
        if muted_until and time.time() < int(muted_until):
            return True
        return False
    except Exception:
        return False

def check_message_safe(text: str) -> bool:
    """تحقق إذا كانت الرسالة آمنة (لا تحتوي على كلمات سيئة)"""
    return len(contains_bad_word(text)) == 0

def apply_respect(uid: int, text: str) -> int:
    bad = contains_bad_word(text)
    if not bad:
        return 0
    dec = RESPECT_PENALTY_PER_BADWORD * len(bad)
    u = ensure_user(uid)
    new_respect = max(0, int(u.get("respect", 100)) - dec)
    update_user_dict(uid, {"respect": new_respect})
    
    # تطبيق الحظر/الكتم
    if new_respect <= FULL_BAN_THRESHOLD:
        update_user_dict(uid, {"banned_full": True})
    elif new_respect <= PARTIAL_BAN_THRESHOLD:
        mute_until = int(time.time() + PARTIAL_BAN_DAYS * 24 * 3600)
        update_user_dict(uid, {"muted_until": mute_until})
    return dec

def review_history_and_penalize(reporter_uid: int, partner_uid: int, history_list: list):
    if not partner_uid:
        return (0, 0, 0, 0)
    
    hist = history_list[-MAX_HISTORY_TO_REVIEW:] if history_list else []
    total_bad = 0
    for item in hist:
        if isinstance(item, dict):
            text = item.get("text", "")
        else:
            text = str(item)
        total_bad += len(contains_bad_word(text))
    
    penalty = total_bad * RESPECT_PENALTY_PER_BADWORD
    p = ensure_user(partner_uid)
    old_respect = int(p.get("respect", 100))
    new_respect = max(0, old_respect - penalty)
    update_user_dict(partner_uid, {"respect": new_respect})
    
    # تطبيق العقوبات
    if new_respect <= FULL_BAN_THRESHOLD:
        update_user_dict(partner_uid, {"banned_full": True})
    elif new_respect <= PARTIAL_BAN_THRESHOLD:
        mute_until = int(time.time() + PARTIAL_BAN_DAYS * 24 * 3600)
        update_user_dict(partner_uid, {"muted_until": mute_until})
    
    return (len(hist), total_bad, penalty, new_respect)
