# Moderation.py
import time
from typing import List
from storage import ensure_user, update_user_dict
from config import RESPECT_PENALTY_PER_BADWORD, PARTIAL_BAN_THRESHOLD, FULL_BAN_THRESHOLD, PARTIAL_BAN_DAYS, MAX_HISTORY_TO_REVIEW

# قائمة كلمات سيئة مبدئية — عدّلها حسب حاجتك
BAD_WORDS = {"****", "كلمةسيئة"}  # استبدل بقائمتك الحقيقية

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
        t = t.replace(w, "*" * len(w))
    return t

def apply_respect(uid: int, text: str) -> int:
    bad = contains_bad_word(text)
    if not bad:
        return 0
    dec = RESPECT_PENALTY_PER_BADWORD * len(bad)
    u = ensure_user(uid)
    new_respect = max(0, int(u.get("respect", 100)) - dec)
    update_user_dict(uid, {"respect": new_respect})
    # apply bans/mutes
    if new_respect <= FULL_BAN_THRESHOLD:
        update_user_dict(uid, {"banned_full": True})
    elif new_respect <= PARTIAL_BAN_THRESHOLD:
        mute_until = int(time.time() + PARTIAL_BAN_DAYS * 24 * 3600)
        update_user_dict(uid, {"muted_until": mute_until})
    return dec

def review_history_and_penalize(reporter_uid: int, partner_uid: int, history_list: list):
    if not partner_uid:
        return (0, 0, 0, 0)
    hist = history_list[-MAX_HISTORY_TO_REVIEW:]
    total_bad = 0
    for item in hist:
        text = item.get("text") if isinstance(item, dict) else str(item)
        total_bad += len(contains_bad_word(text))
    penalty = total_bad * RESPECT_PENALTY_PER_BADWORD
    p = ensure_user(partner_uid)
    new_respect = max(0, int(p.get("respect", 100)) - penalty)
    update_user_dict(partner_uid, {"respect": new_respect})
    if new_respect <= FULL_BAN_THRESHOLD:
        update_user_dict(partner_uid, {"banned_full": True})
    elif new_respect <= PARTIAL_BAN_THRESHOLD:
        mute_until = int(time.time() + PARTIAL_BAN_DAYS * 24 * 3600)
        update_user_dict(partner_uid, {"muted_until": mute_until})
    return (len(hist), total_bad, penalty, new_respect)
