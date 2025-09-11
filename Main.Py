import os
import time
import traceback
import telebot
from flask import Flask, request
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    Message,
)

# ---------- استدعاء الإعدادات ----------
import config
from storage import load_users, save_users, users, ensure_user
from Profile_manger import (
    sanitize_name,
    sanitize_age,
    profile_text,
    append_history,
    end_session,
    start_history,
)
from Moderation import is_muted, apply_respect, review_history_and_penalize
from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
from messages import (
    delayed_send,
    get_welcome_message,
    WELCOME,
    HELP,
    SEARCHING,
    NO_MATCH,
    INTRO_PARTNER,
    LEAVE_CONFIRM,
    LEAVE_TOO_SOON,
    LEFT_YOU,
    LEFT_PARTNER,
    REPORT_CONFIRM,
    REPORT_OK,
    REPORT_RESULT,
    MUTED,
    BANNED,
)

# ---------- فلترة الكلمات السيئة ----------
try:
    from Bad_word import contains_bad_word, censor_text
except Exception:
    def contains_bad_word(text): return False
    def censor_text(text): return text

# ---------- إعداد البوت ----------
TOKEN = getattr(config, "TOKEN", None) or os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN مفقود")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ---------- الحالات ----------
STATE_REGISTER_NAME = "REGISTER_NAME"   # اسم جديد أول مرة
STATE_AWAIT_GENDER = "AWAIT_GENDER"
STATE_AWAIT_NAME = "AWAIT_NAME"         # تعديل اسم
STATE_AWAIT_AGE = "AWAIT_AGE"
STATE_CHOOSE_TOPIC = "CHOOSE_TOPIC"
STATE_CHOOSE_TARGET_GENDER = "CHOOSE_TARGET_GENDER"
STATE_SEARCHING = "SEARCHING"
STATE_CONFIRM_LEAVE = "CONFIRM_LEAVE"
STATE_CONFIRM_REPORT = "CONFIRM_REPORT"

# ---------- كيبوردات ----------
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
    for i in range(0, len(config.TOPICS), 2):
        row = [KeyboardButton(config.TOPICS[i])]
        if i + 1 < len(config.TOPICS):
            row.append(KeyboardButton(config.TOPICS[i+1]))
        kb.add(*row)
    return kb

def target_gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for tg in getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"]):
        kb.add(KeyboardButton(tg))
    return kb

def yes_no_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# ---------- تحميل المستخدمين ----------
load_users()

def update_user(uid, updates: dict):
    ensure_user(uid)
    users[uid].update(updates)
    try: save_users()
    except Exception as e: print(f"[SAVE USER ERROR] {e}")

# ---------- إرسال آمن ----------
def safe_delayed_send(uid, text, delay=0.0, **kwargs):
    try:
        delayed_send(bot, uid, text, delay=delay, **kwargs)
    except Exception as e:
        print(f"[SEND ERROR] {e} | text={text}")
        try: bot.send_message(uid, text, **{k:v for k,v in kwargs.items() if k!="delay"})
        except: pass

# ---------- /start ----------
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    print(f"[START] user={uid}")

    # رسالة ترحيب عشوائية
    safe_delayed_send(uid, get_welcome_message("START"), reply_markup=ReplyKeyboardRemove())

    # طلب الاسم لأول مرة
    update_user(uid, {"state": STATE_REGISTER_NAME})
    safe_delayed_send(uid, "✏️ ما اسمك؟", reply_markup=ReplyKeyboardRemove())

# ---------- /help ----------
@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    if users[uid].get("banned_full"): return
    safe_delayed_send(uid, HELP, delay=0.0,
        reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))

# ---------- ping ----------
@bot.message_handler(commands=["ping"])
def cmd_ping(m: Message):
    bot.send_message(m.chat.id, "pong")

# ---------- on_text ----------
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"): return

    state = u.get("state") or ""

    # تسجيل أول اسم
    if state == STATE_REGISTER_NAME:
        handle_name_registration(uid, txt); return
    # تعديل اسم
    if state == STATE_AWAIT_NAME:
        handle_edit_name(uid, txt); return
    if state == STATE_AWAIT_GENDER:
        handle_gender(uid, txt); return
    if state == STATE_AWAIT_AGE:
        handle_edit_age(uid, txt); return
    if state == STATE_CHOOSE_TOPIC:
        handle_topic_selection(uid, txt); return
    if state == STATE_CHOOSE_TARGET_GENDER:
        handle_target_gender(uid, txt); return
    if state == STATE_CONFIRM_LEAVE:
        handle_leave_confirm(uid, u, txt); return
    if state == STATE_CONFIRM_REPORT:
        handle_report_confirm(uid, u, txt); return

    # الأزرار
    if txt == "👤 ملفي":
        safe_delayed_send(uid, profile_text(u), reply_markup=main_menu(in_chat=bool(u.get("partner")))); return
    if txt == "✏️ تعديل الاسم":
        update_user(uid, {"state": STATE_AWAIT_NAME})
        safe_delayed_send(uid, "أدخل الاسم الجديد:", reply_markup=ReplyKeyboardRemove()); return
    if txt == "🎂 تعديل العمر":
        update_user(uid, {"state": STATE_AWAIT_AGE})
        safe_delayed_send(uid, "أدخل العمر الجديد (10–120):", reply_markup=ReplyKeyboardRemove()); return
    if txt == "🆘 مساعدة":
        safe_delayed_send(uid, HELP, reply_markup=main_menu(in_chat=bool(u.get("partner")))); return
    if txt == "🔍 البحث عن دردشة":
        handle_search_request(uid); return

    # إذا في محادثة
    if u.get("partner"):
        handle_chat_message(uid, txt, u); return

    # غير مفهوم
    safe_delayed_send(uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", reply_markup=main_menu(in_chat=False))

# ---------- اسم أول مرة ----------
def handle_name_registration(uid, txt):
    name = sanitize_name(txt)
    if not (2 <= len(name) <= 30):
        safe_delayed_send(uid, "❌ الاسم غير صالح، حاول مجددًا:"); return
    update_user(uid, {"name": name, "state": STATE_AWAIT_GENDER})

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(*[KeyboardButton(g) for g in config.GENDERS])
    safe_delayed_send(uid, "💡 اختر جنسك:", reply_markup=kb)

# ---------- تعديل الاسم ----------
def handle_edit_name(uid, txt):
    name = sanitize_name(txt)
    update_user(uid, {"name": name, "state": None})
    safe_delayed_send(uid, f"✅ تم تحديث الاسم إلى: {name}", reply_markup=main_menu(False))

# ---------- الجنس ----------
def handle_gender(uid, txt):
    if txt not in config.GENDERS:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(*[KeyboardButton(g) for g in config.GENDERS])
        safe_delayed_send(uid, "❌ اختر: ذكر / أنثى", reply_markup=kb); return
    update_user(uid, {"gender": txt, "state": STATE_AWAIT_AGE})
    safe_delayed_send(uid, f"✅ تم حفظ الجنس: {txt}")
    safe_delayed_send(uid, "🎂 ما عمرك؟ (10–120)", reply_markup=ReplyKeyboardRemove())

# ---------- العمر ----------
def handle_edit_age(uid, txt):
    age = sanitize_age(txt)
    if not age:
        safe_delayed_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120."); return
    update_user(uid, {"age": age, "state": None})
    safe_delayed_send(uid, f"✅ تم حفظ العمر: {age}", reply_markup=main_menu(False))

# ---------- ... باقي الدوال (البحث، التطابق، مغادرة، إلخ) تبقى كما هي ----------

# ---------- بدء البحث عن دردشة (يعرض قائمة المواضيع) ----------
def handle_search_request(uid):
    ensure_user(uid)
    u = users[uid]
    if u.get("partner"):
        safe_delayed_send(uid, "⚠️ أنت بالفعل في دردشة!", reply_markup=main_menu(in_chat=True))
        return
    update_user(uid, {"state": STATE_CHOOSE_TOPIC})
    safe_delayed_send(uid, "اختر موضوع النقاش:", reply_markup=topics_menu())

# ---------- اختيار الموضوع ----------
def handle_topic_selection(uid, txt):
    txt = txt.strip()
    if txt not in config.TOPICS:
        safe_delayed_send(uid, "❌ اختر موضوعًا صالحًا من القائمة.", reply_markup=topics_menu())
        return
    update_user(uid, {"topic": txt, "state": STATE_CHOOSE_TARGET_GENDER})
    safe_delayed_send(uid, f"تم اختيار الموضوع: {txt}\nالآن اختر جنس الطرف الذي تريده:", reply_markup=target_gender_menu())

# ---------- اختيار جنس الشريك وبدء البحث ----------
def handle_target_gender(uid, txt):
    txt = txt.strip()
    valid = getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"])
    valid_with_any = valid + ["أي"]
    if txt not in valid_with_any:
        safe_delayed_send(uid, f"❌ اختر: {' / '.join(valid_with_any)}", reply_markup=target_gender_menu())
        return

    if "رجل" in txt:
        target = "male"
    elif "امرأة" in txt or "امرأ" in txt:
        target = "female"
    else:
        target = "any"

    u = users[uid]
    topic = u.get("topic")
    update_user(uid, {"target_gender": target, "state": STATE_SEARCHING})

    # رسالة ترحيب خاصة للموضوع
    topic_key = _topic_key(topic)
    safe_delayed_send(uid, get_welcome_message(topic_key))
    safe_delayed_send(uid, SEARCHING, reply_markup=main_menu(in_chat=False))

    # ملاحظة مهمة: توقيعات add_to_wait/try_match كما في matchmaking.py لديك:
    # add_to_wait(topic, uid, target)  - try_match(uid, topic)
    try:
        add_to_wait(topic, uid, target)
    except Exception as e:
        print(f"[add_to_wait ERROR] {e}")

    # حاول المطابقة (التوقيع: try_match(uid, topic))
    partner = None
    try:
        partner = try_match(uid, topic)
    except Exception as e:
        print(f"[try_match ERROR] {e}")

    # إذا نَجَحت المطابقة، جهّز الجلسة
    if partner:
        try:
            pid = int(partner)
            update_user(uid, {"partner": pid, "state": None, "chat_started_at": time.time()})
            update_user(pid, {"partner": uid, "state": None, "chat_started_at": time.time()})
            try:
                start_history(uid); start_history(pid)
            except Exception:
                pass
            safe_delayed_send(uid, INTRO_PARTNER, reply_markup=main_menu(in_chat=True))
            try:
                safe_delayed_send(pid, INTRO_PARTNER, reply_markup=main_menu(in_chat=True))
            except Exception:
                pass
        except Exception as e:
            print(f"[MATCH SETUP ERROR] {e}")

    # (لا حاجة لتمرير uid/topic لبدء watcher — watcher مُشغّل عامة عند الإقلاع)
    # إذا تريد أن تضمن إعادة تشغيل watcher للـ bot يمكنك استدعاؤه لكن توقيعه في matchmaking.py هو start_timeout_watcher(bot)

# ---------- مغادرة الدردشة ----------
def handle_leave_request(uid):
    ensure_user(uid)
    u = users[uid]
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    if elapsed < getattr(config, "LEAVE_DELAY", 30):
        safe_delayed_send(uid, LEAVE_TOO_SOON.format(remain=int(getattr(config, "LEAVE_DELAY", 30) - elapsed)))
        return
    update_user(uid, {"state": STATE_CONFIRM_LEAVE})
    safe_delayed_send(uid, LEAVE_CONFIRM, reply_markup=yes_no_menu())

def handle_leave_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        if pid:
            try:
                # قد يعمل end_session بمعرفين أو بكائنات — نحاول عدة محاولات
                end_session(uid, pid)
            except Exception:
                try:
                    end_session(u, users.get(pid))
                except Exception:
                    try:
                        end_session(uid)
                        end_session(pid)
                    except Exception as e:
                        print(f"[END_SESSION ERROR] {e}")
            update_user(uid, {"partner": None, "state": None, "chat_started_at": None})
            update_user(pid, {"partner": None, "state": None, "chat_started_at": None})
            safe_delayed_send(uid, "لقد غادرت الدردشة.", reply_markup=main_menu(in_chat=False))
            try:
                safe_delayed_send(pid, "شريكك غادر الدردشة.", reply_markup=main_menu(in_chat=False))
            except Exception:
                pass
        else:
            update_user(uid, {"state": None})
            safe_delayed_send(uid, "لم يتم العثور على شريك حالي.")
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_delayed_send(uid, "تم الإلغاء. تابع الدردشة 👌")
    else:
        safe_delayed_send(uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())

# ---------- الإبلاغ (نص عادي نعم/لا مُرسَل من لوحة yes_no_menu) ----------
def handle_report_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        try:
            # دالة review_history_and_penalize قد ترجع نتائج مختلفة حسب implementation
            result = review_history_and_penalize(uid, pid, u.get("history", []))
        except Exception as e:
            print(f"[review_history_and_penalize ERROR] {e}")
            result = None
        update_user(uid, {"state": None})
        safe_delayed_send(uid, REPORT_OK)
        if result:
            try:
                safe_delayed_send(uid, REPORT_RESULT.format(lines=result[0], respect=u.get("respect", "—")))
            except Exception:
                pass
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_delayed_send(uid, "تم الإلغاء. شكراً لحرصك.")
    else:
        safe_delayed_send(uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())
        return

    # بعدها أرسل زر المغادرة دائمًا (حتى لا تبقى أزرار نعم/لا معلقة)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🚪 مغادرة الدردشة"))
    safe_delayed_send(uid, "هل تريد الآن مغادرة الدردشة؟", reply_markup=kb)

# ---------- تمرير الرسائل بين الشركاء ----------
def handle_chat_message(uid, txt, u):
    # تحقق حالة الحظر/الـ mute
    muted, left = is_user_muted(uid)
    if muted:
        safe_delayed_send(uid, MUTED.format(left=left or 60))
        return

    # فلترة كلمات سيئة
    try:
        if contains_bad_word(txt):
            txt_to_send = censor_text(txt)
            safe_delayed_send(uid, "⚠️ تم تعديل رسالتك لاحتوائها على كلمات غير لائقة.")
        else:
            txt_to_send = txt
    except Exception:
        txt_to_send = txt

    # تطبيق نظام الاحترام (قد يرجع رسالة إن تطلب الأمر)
    try:
        msg = apply_respect(uid, txt_to_send)
        if msg:
            safe_delayed_send(uid, msg)
    except Exception:
        pass

    # حفظ السجل (بشكل مرن)
    try:
        append_history_safe(uid, txt_to_send)
    except Exception:
        pass

    # إرسال للشريك
    pid = u.get("partner")
    if not pid or pid not in users:
        update_user(uid, {"partner": None})
        safe_delayed_send(uid, "لا يوجد شريك حالي — عد إلى القائمة.", reply_markup=main_menu(in_chat=False))
        return

    try:
        bot.send_message(pid, f"💬 {txt_to_send}")
    except Exception as e:
        print(f"[SEND TO PARTNER ERROR] {e}")
        safe_delayed_send(uid, "حدث خطأ أثناء إرسال الرسالة إلى الشريك.")

# ---------- Webhook endpoint ----------
@app.route(f"/{getattr(config, 'WEBHOOK_PATH', 'webhook')}", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"[WEBHOOK PROCESS ERROR] {e}\n{traceback.format_exc()}")
    return "", 200

def set_webhook():
    url = os.environ.get("WEBHOOK_URL") or getattr(config, "WEBHOOK_URL", None)
    path = getattr(config, "WEBHOOK_PATH", "webhook")
    if not url:
        raise RuntimeError("WEBHOOK_URL مفقود. ضعه في Environment أو config.WEBHOOK_URL")
    bot.remove_webhook()
    bot.set_webhook(f"{url}/{path}")
    print(f"[WEBHOOK] Set to {url}/{path}")

# ---------- تهيئة Matchmaking watcher إن وُجد ----------
try:
    start_timeout_watcher(bot)
except Exception:
    try:
        start_timeout_watcher()
    except Exception:
        pass

# ---------- نقطة التشغيل ----------
if __name__ == "__main__":
    try:
        load_users()
    except Exception as e:
        print(f"[LOAD_USERS ERROR] {e}")
    try:
        set_webhook()
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
    port = int(os.environ.get("PORT", getattr(config, "PORT", 5000)))
    print(f"[RUN] Webhook listening on port {port}…")
    app.run(host="0.0.0.0", port=port)
