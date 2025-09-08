# Main.py
import os
import telebot
from flask import Flask, request
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message

from config import TOKEN, ADMIN_CHAT_ID, TOPICS, GENDERS, TARGET_GENDERS, LEAVE_DELAY, WEBHOOK_PATH
from storage import load_users, save_users, ensure_user, users
from Profile_manger import sanitize_name, sanitize_age, profile_text, append_history, end_session, start_history
from Moderation import is_muted, apply_respect, review_history_and_penalize
from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
from messages import (WELCOME, HELP, SEARCHING, INTRO_PARTNER, NO_MATCH,
                      LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER,
                      REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED,
                      delayed_send, get_welcome_message)

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

# ==================== أوامر البوت ====================
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]

    if u.get("banned_full"):
        delayed_send(bot, uid, BANNED, delay=0.2)
        return

    # مستخدم جديد
    if not u.get("gender"):
        u["state"] = "AWAIT_GENDER"
        save_users()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("ذكر"), KeyboardButton("أنثى"), KeyboardButton("أخرى"))
        delayed_send(bot, uid, "اختر الجنس (مرة واحدة فقط):", delay=0.2, reply_markup=kb)
        return

    # مستخدم عائد
    u["state"] = None
    save_users()
    delayed_send(bot, uid, "مرحبًا من جديد! اختر من القائمة:", delay=0.2,
                 reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return
    delayed_send(bot, uid, HELP, delay=0.2,
                 reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["profile"])
def cmd_profile(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    delayed_send(bot, uid, profile_text(users[uid]), delay=0.2,
                 reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))

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

    # حالات التسجيل
    if state == "AWAIT_GENDER": handle_gender(uid, txt); return
    if state == "AWAIT_NAME": handle_name(uid, txt); return
    if state == "AWAIT_AGE": handle_age(uid, txt); return

    # أزرار القائمة
    if txt == "👤 ملفي":
        delayed_send(bot, uid, profile_text(u), delay=0.2,
                     reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return
    if txt == "✏️ تعديل الاسم":
        u["state"] = "EDIT_NAME"; save_users()
        delayed_send(bot, uid,"أدخل الاسم الجديد:",delay=0.2,reply_markup=ReplyKeyboardRemove())
        return
    if state == "EDIT_NAME": handle_edit_name(uid, txt); return
    if txt == "🎂 تعديل العمر":
        u["state"] = "EDIT_AGE"; save_users()
        delayed_send(bot, uid,"أدخل العمر الجديد (10–120):",delay=0.2,reply_markup=ReplyKeyboardRemove())
        return
    if state == "EDIT_AGE": handle_edit_age(uid, txt); return
    if txt == "🆘 مساعدة":
        delayed_send(bot, uid, HELP, delay=0.2,
# Main.py
import os
import time
import telebot
from flask import Flask, request
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message

from config import TOKEN, ADMIN_CHAT_ID, TOPICS, GENDERS, TARGET_GENDERS, LEAVE_DELAY, WEBHOOK_PATH
from storage import load_users, save_users, ensure_user, users
from Profile_manger import sanitize_name, sanitize_age, profile_text, append_history, end_session, start_history
from Moderation import is_muted, apply_respect, review_history_and_penalize
from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
from messages import (
    WELCOME, HELP, SEARCHING, INTRO_PARTNER, NO_MATCH,
    LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER,
    REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED,
    delayed_send, get_welcome_message, GENERAL_WELCOME_MESSAGES
)

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

# ==================== أوامر البوت ====================
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]

    if u.get("banned_full"):
        delayed_send(bot, uid, BANNED, delay=0.4)
        return

    # مستخدم جديد
    if not u.get("gender"):
        # رسالة ترحيب ثابتة عند البداية
        fixed_welcome = "\n".join([
            "لقد وصلت الى طريق مسدود.. بس منفتحو كرمالك 😎",
            "تفضل يا مولاي...",
            "هوووووب شلاح من رجلك وفوت يا مولاي",
            "شلاح ولاااك............. من رجلك من رجلك 😂",
            "اي تفضل تفضل تفضل ❤️❤️"
        ])
        delayed_send(bot, uid, fixed_welcome, delay=0.4, reply_markup=ReplyKeyboardRemove())

        u["state"] = "AWAIT_GENDER"
        save_users()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("ذكر"), KeyboardButton("أنثى"), KeyboardButton("أخرى"))
        delayed_send(bot, uid, "اختر الجنس (مرة واحدة فقط):", delay=0.8, reply_markup=kb)
        return

    # مستخدم عائد
    u["state"] = None
    save_users()
    delayed_send(bot, uid, f"مرحبًا من جديد! اختر من القائمة:", delay=0.4,
                 reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return
    delayed_send(bot, uid, HELP, delay=0.2,
                 reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["profile"])
def cmd_profile(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    delayed_send(bot, uid, profile_text(users[uid]), delay=0.2,
                 reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))

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

    # حالات التسجيل
    if state == "AWAIT_GENDER": handle_gender(uid, txt); return
    if state == "AWAIT_NAME": handle_name(uid, txt); return
    if state == "AWAIT_AGE": handle_age(uid, txt); return

    # أزرار القائمة
    if txt == "👤 ملفي":
        delayed_send(bot, uid, profile_text(u), delay=0.2,
                     reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return
    if txt == "✏️ تعديل الاسم":
        u["state"] = "EDIT_NAME"; save_users()
        delayed_send(bot, uid,"أدخل الاسم الجديد:",delay=0.2,reply_markup=ReplyKeyboardRemove())
        return
    if state == "EDIT_NAME": handle_edit_name(uid, txt); return
    if txt == "🎂 تعديل العمر":
        u["state"] = "EDIT_AGE"; save_users()
        delayed_send(bot, uid,"أدخل العمر الجديد (10–120):",delay=0.2,reply_markup=ReplyKeyboardRemove())
        return
    if state == "EDIT_AGE": handle_edit_age(uid, txt); return
    if txt == "🆘 مساعدة":
        delayed_send(bot, uid, HELP, delay=0.2,
                     reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return
    if txt == "🔍 البحث عن دردشة": handle_search_request(uid); return

    # اختيار موضوع / الفئة
    if state in ["CHOOSE_TOPIC", "CHOOSE_TARGET_GENDER"]:
        handle_topic_selection(uid, txt); return

    # داخل الدردشة
    if u.get("partner"): handle_chat_message(uid, txt, u); return

    # افتراضي
    delayed_send(bot, uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", delay=0.2,
                 reply_markup=main_menu(in_chat=False))

# ==================== دوال المساعدة للتسجيل ========
def handle_gender(uid, txt):
    u = users[uid]
    if txt not in GENDERS:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("ذكر"), KeyboardButton("أنثى"), KeyboardButton("أخرى"))
        delayed_send(bot, uid, "اختر من الأزرار: ذكر / أنثى / أخرى", delay=0.3, reply_markup=kb)
        return
    u["gender"]=txt; u["state"]="AWAIT_NAME"; save_users()
    delayed_send(bot, uid, "أدخل اسمك (٢–٣٠ حرفًا، بدون أرقام):", delay=0.3, reply_markup=ReplyKeyboardRemove())

def handle_name(uid, txt):
    u = users[uid]
    name = sanitize_name(txt)
    if not name: delayed_send(bot, uid,"❌ الاسم غير صالح. حاول مجددًا:",delay=0.3); return
    u["name"]=name; u["state"]="AWAIT_AGE"; save_users()
    delayed_send(bot, uid,"أدخل عمرك (10–120):",delay=0.3)

def handle_age(uid, txt):
    u = users[uid]
    age = sanitize_age(txt)
    if age is None:
        delayed_send(bot, uid,"❌ العمر غير صالح. أدخل رقمًا بين 10 و120:",delay=0.3)
        return
    u["age"] = age
    u["state"] = None
    save_users()

    # إرسال رسالة عشوائية حسب topic إذا اختير، أو ترحيب ثابت عند البداية
    topic = u.get("topic")
    if topic:
        delayed_send(bot, uid, get_welcome_message(topic=topic), delay=0.4)
    delayed_send(bot, uid,"✅ تم الحفظ.\n"+profile_text(u),delay=0.4,reply_markup=main_menu(in_chat=False))
    delayed_send(bot, uid,"اضغط: 🔍 البحث عن دردشة عند جاهزيتك.",delay=0.5)

# بقية الدوال (تعديل الاسم/العمر، البحث عن دردشة، الدردشة، الإبلاغ، مغادرة الدردشة، Webhook، إلخ) تبقى كما في الكود السابق
# فقط تأكد أن كل دالة تستدعي delayed_send() بشكل صحيح بعد أي تحديث للحالة

# ==================== تعديل الاسم والعمر ====================
def handle_edit_name(uid, txt):
    u = users[uid]; name = sanitize_name(txt)
    if not name: delayed_send(bot, uid,"❌ الاسم غير صالح. حاول مجددًا:",delay=0.2); return
    u["name"] = name; u["state"] = None; save_users()
    delayed_send(bot, uid,"✅ تم التحديث.\n"+profile_text(u),delay=0.2,reply_markup=main_menu(in_chat=bool(u.get("partner"))))

def handle_edit_age(uid, txt):
    u = users[uid]; age = sanitize_age(txt)
    if age is None: delayed_send(bot, uid,"❌ العمر غير صالح. أدخل رقمًا بين 10 و120:",delay=0.2); return
    u["age"] = age; u["state"] = None; save_users()
    delayed_send(bot, uid,"✅ تم التحديث.\n"+profile_text(u),delay=0.2,reply_markup=main_menu(in_chat=bool(u.get("partner"))))

# ==================== البحث عن دردشة ====================
def handle_search_request(uid):
    u = users[uid]
    if not (u.get("gender") and u.get("name") and u.get("age")):
        delayed_send(bot, uid,"⚠️ أكمل التسجيل أولًا عبر /start.",delay=0.2); return
    u["state"]="CHOOSE_TOPIC"; save_users()
    delayed_send(bot, uid,"اختر موضوع النقاش:",delay=0.2,reply_markup=topics_menu())

def handle_topic_selection(uid, txt):
    u = users[uid]
    if u["state"]=="CHOOSE_TOPIC":
        if txt not in TOPICS: delayed_send(bot, uid,"❌ اختر من الأزرار:",delay=0.2,reply_markup=topics_menu()); return
        u["topic"]=txt; u["state"]="CHOOSE_TARGET_GENDER"; save_users()
        delayed_send(bot, uid,"اختر الجنس الذي تود الدردشة معه:",delay=0.2,reply_markup=target_gender_menu())
        return
    if u["state"]=="CHOOSE_TARGET_GENDER":
        if txt not in TARGET_GENDERS: delayed_send(bot, uid,"❌ اختر من الأزرار:",delay=0.2,reply_markup=target_gender_menu()); return
        u["search_pref"]="أي" if txt=="أي" else txt; u["state"]=None; save_users()
        add_to_wait(u["topic"], uid, u["search_pref"])
        delayed_send(bot, uid, SEARCHING, delay=0.2, reply_markup=main_menu(in_chat=False))
        partner_id = try_match(uid, u["topic"])
        if partner_id: start_chat(uid, partner_id)

# ==================== دردشة المستخدم ====================
# ... باقي دوال الدردشة كما هي في ملفك السابق بدون تعديل ...
# handle_chat_message, handle_leave_request, handle_leave_confirm, handle_report, start_chat
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
    load_users()
    try:
        set_webhook()
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")

    start_timeout_watcher(bot)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 
