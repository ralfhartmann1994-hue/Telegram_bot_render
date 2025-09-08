# Main.py
import os
import time
import telebot
from flask import Flask, request
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message

from config import TOKEN, ADMIN_CHAT_ID, TOPICS, GENDERS, TARGET_GENDERS, LEAVE_DELAY, WEBHOOK_PATH
from storage import load_users, users, ensure_user
from Profile_manger import sanitize_name, sanitize_age, profile_text, append_history, end_session, start_history
from Moderation import is_muted, apply_respect, review_history_and_penalize
from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
from messages import (WELCOME, HELP, SEARCHING, INTRO_PARTNER, NO_MATCH,
                      LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER,
                      REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED, delayed_send,
                      get_welcome_message)

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN مفقود. أضفه في Render → Environment.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ==================== القوائم ====================
def main_menu(in_chat: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("👤 ملفي"))
    kb.add(KeyboardButton("✏️ تعديل الاسم"), KeyboardButton("🎂 تعديل العمر"))
    kb.add(KeyboardButton("🔍 البحث عن دردشة"))
    if in_chat:
        kb.add(KeyboardButton("🚨 إبلاغ"), KeyboardButton("🚪 مغادرة الدردشة"))
    kb.add(KeyboardButton("🆘 مساعدة"))
    return kb

def topics_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i in range(0, len(TOPICS), 2):
        row = [KeyboardButton(TOPICS[i])]
        if i + 1 < len(TOPICS):
            row.append(KeyboardButton(TOPICS[i+1]))
        kb.add(*row)
    return kb

def target_gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("👨 رجل"), KeyboardButton("👩 امرأة"))
    kb.add(KeyboardButton("أي"))
    return kb

def yes_no_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# ==================== تحديث المستخدم بشكل آمن ====================
def update_user(uid, updates: dict):
    ensure_user(uid)
    users[uid].update(updates)
    # حفظ المستخدمين بشكل آمن في storage
    try:
        from storage import save_users
        save_users()
    except Exception as e:
        print(f"[SAVE USER ERROR] {e}")

# ==================== أوامر البوت ====================
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]

    print(f"[START] UID={uid}, state={u.get('state')}, gender={u.get('gender')}")  # لتتبع المشاكل

    if u.get("banned_full"):
        try:
            delayed_send(bot, uid, BANNED, delay=0.4)
        except Exception as e:
            print(f"[DELAYED_SEND ERROR] {e}")
        return

    # رسالة ترحيب ثابتة للجميع
    welcome_text = (
        "لقد وصلت الى طريق مسدود.. بس منفتحو كرمالك 😎\n"
        "تفضل يا مولاي...\n"
        "هوووووب شلاح من رجلك وفوت يا مولاي\n"
        "شلاح ولاااك............. من رجلك من رجلك 😂\n"
        "اي تفضل تفضل تفضل ❤️❤️"
    )
    try:
        delayed_send(bot, uid, welcome_text, delay=0.4, reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        print(f"[DELAYED_SEND ERROR] {e}")

    # إذا المستخدم جديد (بدون gender)
    if not u.get("gender"):
        u["state"] = "AWAIT_GENDER"
        save_users()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("ذكر"), KeyboardButton("أنثى"), KeyboardButton("أخرى"))
        try:
            delayed_send(bot, uid, "اختر الجنس (مرة واحدة فقط):", delay=0.8, reply_markup=kb)
        except Exception as e:
            print(f"[DELAYED_SEND ERROR] {e}")
        return

    # مستخدم عائد
    u["state"] = None
    save_users()
    try:
        delayed_send(
            bot,
            uid,
            "مرحبًا من جديد! اختر من القائمة:",
            delay=0.4,
            reply_markup=main_menu(in_chat=bool(u.get("partner")))
        )
    except Exception as e:
        print(f"[DELAYED_SEND ERROR] {e}")

@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return
    delayed_send(bot, uid, HELP, delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner"))))

# ==================== معالجة النصوص ====================
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return

    state = u.get("state") or ""

    if state == "AWAIT_GENDER": handle_gender(uid, txt); return
    if state == "AWAIT_NAME": handle_name(uid, txt); return
    if state == "AWAIT_AGE": handle_age(uid, txt); return
    if txt == "👤 ملفي": delayed_send(bot, uid, profile_text(u), delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner")))); return
    if txt == "✏️ تعديل الاسم": update_user(uid, {"state": "EDIT_NAME"}); delayed_send(bot, uid, "أدخل الاسم الجديد:", delay=0.2, reply_markup=ReplyKeyboardRemove()); return
    if state == "EDIT_NAME": handle_edit_name(uid, txt); return
    if txt == "🎂 تعديل العمر": update_user(uid, {"state": "EDIT_AGE"}); delayed_send(bot, uid, "أدخل العمر الجديد (10–120):", delay=0.2, reply_markup=ReplyKeyboardRemove()); return
    if state == "EDIT_AGE": handle_edit_age(uid, txt); return
    if txt == "🆘 مساعدة": delayed_send(bot, uid, HELP, delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner")))); return
    if txt == "🔍 البحث عن دردشة": handle_search_request(uid); return
    if state in ["CHOOSE_TOPIC", "CHOOSE_TARGET_GENDER"]: handle_topic_selection(uid, txt); return
    if u.get("partner"): handle_chat_message(uid, txt, u); return
    delayed_send(bot, uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", delay=0.2, reply_markup=main_menu(in_chat=False))

# ==================== بدء / إنهاء المحادثة ====================
def handle_leave_request(uid, u):
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    if elapsed < LEAVE_DELAY:
        delayed_send(bot, uid, f"لا يمكنك المغادرة قبل {int(LEAVE_DELAY - elapsed)} ثانية.", delay=0.2)
        return
    update_user(uid, {"state": "CONFIRM_LEAVE"})
    delayed_send(bot, uid, "هل تريد حقًا مغادرة الدردشة؟", delay=0.2, reply_markup=yes_no_menu())

def handle_leave_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        p = users.get(pid)
        end_session(u, p)
        delayed_send(bot, uid, "لقد غادرت الدردشة.", delay=0.2, reply_markup=main_menu(in_chat=False))
        if pid and p:
            try:
                delayed_send(bot, pid, "شريكك غادر الدردشة.", delay=0.2, reply_markup=main_menu(in_chat=False))
            except Exception as e:
                print(f"[LEAVE NOTIFY PARTNER] {e}")
        update_user(uid, {"state": None})
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        delayed_send(bot, uid, "تم الإلغاء. تابع الدردشة 👌", delay=0.2)
    else:
        delayed_send(bot, uid, "اختر: نعم ✅ / لا ❌", delay=0.2, reply_markup=yes_no_menu())

# ==================== Webhook + Flask ====================
@app.route(f"/{WEBHOOK_PATH}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

def set_webhook():
    url = os.environ.get("WEBHOOK_URL")
    if not url:
        raise RuntimeError("WEBHOOK_URL مفقود. أضفه في Environment Variables في Render.")
    bot.remove_webhook()
    bot.set_webhook(f"{url}/{WEBHOOK_PATH}")
    print(f"[WEBHOOK] Set to {url}/{WEBHOOK_PATH}")

# ==================== التشغيل الرئيسي ====================
if __name__ == "__main__":
    print("[BOOT] Loading users...")
    from storage import load_users
    load_users()
    print(f"[BOOT] Users loaded: {len(users)}")

    try:
        set_webhook()
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")

    start_timeout_watcher(bot)

    port = int(os.environ.get("PORT", 5000))
    print(f"[RUN] Webhook listening on port {port}…")
    app.run(host="0.0.0.0", port=port)
