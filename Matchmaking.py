# matchmaking.py
import time, threading
from typing import Dict, List
from config import SEARCH_TIMEOUT, TARGET_GENDERS
from storage import users, save_users
from messages import NO_MATCH, delayed_send

# waiting[topic] = list of dicts: {uid, target_gender, since}
waiting: Dict[str, List[dict]] = {}

def add_to_wait(topic: str, uid: int, target_gender: str):
    if topic not in waiting:
        waiting[topic] = []
    # نظّف أي تكرار قديم لنفس المستخدم
    waiting[topic] = [w for w in waiting[topic] if w["uid"] != uid]
    waiting[topic].append({"uid": uid, "target_gender": target_gender, "since": time.time()})
    users[uid]["search_since"] = time.time()
    users[uid]["topic"] = topic
    users[uid]["search_pref"] = target_gender
    save_users()

def remove_from_wait(uid: int):
    for t in list(waiting.keys()):
        waiting[t] = [w for w in waiting[t] if w["uid"] != uid]

def target_matches(me_wants: str, partner_gender: str) -> bool:
    if me_wants == "أي":
        return True
    if me_wants == "👨 رجل":
        return partner_gender == "ذكر"
    if me_wants == "👩 امرأة":
        return partner_gender == "أنثى"
    return True

def try_match(uid: int, topic: str) -> int | None:
    """محاولة مطابقة فورية ضمن نفس الموضوع بشرط تفضيلات الجنس المتبادلة."""
    me = users.get(uid)
    if not me:
        return None
    me_wants = me.get("search_pref")
    my_gender = me.get("gender")
    if topic not in waiting:
        return None

    for i, w in enumerate(waiting[topic]):
        other_id = w["uid"]
        if other_id == uid:
            continue
        other = users.get(other_id)
        if not other:
            continue
        # تحقق تفضيلات الجنس المتبادلة
        if not target_matches(me_wants, other.get("gender") or ""):
            continue
        other_wants = other.get("search_pref") or "أي"
        if not target_matches(other_wants, my_gender or ""):
            continue
        # مطابقة!
        waiting[topic].pop(i)
        remove_from_wait(uid)
        return other_id
    return None

def start_timeout_watcher(bot):
    """خيط خفيف يفحص من تجاوز 30 دقيقة ويرسِل له رسالة عدم وجود شريك."""
    def loop():
        while True:
            now = time.time()
            for t, lst in list(waiting.items()):
                expired = [w for w in lst if now - w["since"] >= SEARCH_TIMEOUT]
                if not expired:
                    continue
                for w in expired:
                    uid = w["uid"]
                    # نظّف من الانتظار
                    remove_from_wait(uid)
                    u = users.get(uid)
                    if u and not u.get("partner"):
                        # أرسل له رسالة عدم العثور
                        try:
                            delayed_send(bot, uid, NO_MATCH, delay=0.6)
                        except Exception as e:
                            print(f"[TIMEOUT MSG] {e}")
                        u["search_since"] = None
                        u["search_pref"] = None
                        save_users()
                # أبقِ فقط من لم ينته وقتهم
                waiting[t] = [w for w in lst if now - w["since"] < SEARCH_TIMEOUT]
            time.sleep(10)
    th = threading.Thread(target=loop, daemon=True)
    th.start()
