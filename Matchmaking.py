# Matchmaking.py
import threading
import time
from typing import List
from config import SEARCH_TIMEOUT, SEARCH_CHECK_INTERVAL
from storage import ensure_user, update_user_dict
import importlib

_messages = importlib.import_module("messages")
_wait_lock = threading.RLock()
_waiting: List[dict] = []  # entries: {"topic", "uid", "target", "ts"}

def add_to_wait(topic, uid, target="any"):
    with _wait_lock:
        # prevent duplicate entries
        for e in _waiting:
            if e["uid"] == uid:
                e.update({"topic": topic, "target": target, "ts": time.time()})
                return
        _waiting.append({"topic": topic, "uid": uid, "target": target, "ts": time.time()})

def remove_from_wait(uid):
    with _wait_lock:
        for i, e in enumerate(list(_waiting)):
            if e["uid"] == uid:
                _waiting.pop(i)
                return True
    return False

def try_match(uid, topic):
    with _wait_lock:
        me = None
        for e in _waiting:
            if e["uid"] == uid:
                me = e
                break
        if not me:
            return None
        # Try find match (FIFO)
        for e in _waiting:
            if e is me:
                continue
            if e["topic"] == me["topic"]:
                # simple matching ignoring target for now (can expand)
                partner_uid = e["uid"]
                # remove both from waiting
                try:
                    _waiting.remove(me)
                except ValueError:
                    pass
                try:
                    _waiting.remove(e)
                except ValueError:
                    pass
                return partner_uid
    return None

# watcher thread
_watcher = None
_stop_event = None

def _watcher_thread(bot=None, stop_event=None):
    while not stop_event.is_set():
        now = time.time()
        timed_out = []
        with _wait_lock:
            for e in list(_waiting):
                if now - e["ts"] >= SEARCH_TIMEOUT:
                    timed_out.append(e)
        for e in timed_out:
            with _wait_lock:
                try:
                    _waiting.remove(e)
                except Exception:
                    pass
            try:
                if bot:
                    bot.send_message(e["uid"], _messages.NO_MATCH + "\n\n🔁 جرّب مرة أخرى — سنحاول العثور على شريك لاحقاً.")
                else:
                    print(f"[Matchmaking] timeout notify {e['uid']}")
                update_user_dict(e["uid"], {"state": None})
            except Exception as ex:
                print(f"[Matchmaking notify ERROR] {ex}")
        stop_event.wait(SEARCH_CHECK_INTERVAL)

def start_timeout_watcher(bot=None):
    global _watcher, _stop_event
    if _watcher and _watcher.is_alive():
        return
    _stop_event = threading.Event()
    _watcher = threading.Thread(target=_watcher_thread, args=(bot, _stop_event), daemon=True)
    _watcher.start()

def stop_timeout_watcher():
    global _stop_event
    if _stop_event:
        _stop_event.set()
