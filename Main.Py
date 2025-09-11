# Main.py
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

# ---------- إعدادات واستدعاءات ----------
import config
from storage import load_users, save_users, users, ensure_user

# إدارة الملف الشخصي، فلترة، مودريشن، ميتشماكينغ، ورسائل
from Profile_manger import sanitize_name, sanitize_age, profile_text, append_history, end_session, start_history
from Moderation import is_muted, apply_respect, review_history_and_penalize
from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
from messages import delayed_send, get_welcome_message, WELCOME, HELP, SEARCHING, NO_MATCH, INTRO_PARTNER, LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER, REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED

# Bad_word (إن وُجد)
try:
    from Bad_word import contains_bad_word, censor_text
except Exception:
    def contains_bad_word(text):
        return False
    def censor_text(text):
        return text

# ---------- البوت وفلَسْك ----------
TOKEN = getattr(config, "TOKEN", None) or os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN غير موجود في config.TOKEN أو متغير البيئة TELEGRAM_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ---------- حالات واضحة (state constants) ----------
STATE_REGISTER_NAME = "REGISTER_NAME"     # بعد /start: ننتظر اسم المستخدم
STATE_REGISTER_GENDER = "REGISTER_GENDER" # بعد الاسم: ننتظر الجنس (زر)
STATE_REGISTER_AGE = "REGISTER_AGE"       # بعد الجنس: ننتظر العمر (نص)
STATE_EDIT_NAME = "EDIT_NAME"             # عند الضغط على "✏️ تعديل الاسم"
STATE_EDIT_AGE = "EDIT_AGE"               # عند الضغط على "🎂 تعديل العمر"
STATE_CHOOSE_TOPIC = "CHOOSE_TOPIC"
STATE_CHOOSE_TARGET_GENDER = "CHOOSE_TARGET_GENDER"
STATE_SEARCHING = "SEARCHING"
STATE_CONFIRM_LEAVE = "CONFIRM_LEAVE"
STATE_CONFIRM_REPORT = "CONFIRM_REPORT"

# ---------- كيبوردات مساعدة ----------
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

def gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for g in getattr(config, "GENDERS", ["ذكر", "أنثى"]):
        kb.add(KeyboardButton(g))
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

# ---------- تحديث وحفظ المستخدم ----------
def update_user(uid, updates: dict):
    ensure_user(uid)
    users[uid].update(updates)
    try:
        save_users()
    except Exception as e:
        print(f"[SAVE USER ERROR] {e}")

# ---------- غلاف للإرسال آمن (لا نمرّر 'delay' إلى bot.send_message) ----------
def safe_send(uid, text, **kwargs):
    """
    استعمل هذه الدالة بدلاً من bot.send_message مباشرة.
    دالة messages.delayed_send تأخذ (bot, chat_id, text, **kwargs) وتُرسِل مباشرة.
    """
    try:
        delayed_send(bot, uid, text, **kwargs)
    except Exception as e:
        # طباعة الخطأ مع ملخص صغير
        print(f"[SEND_MESSAGE ERROR] {e} | chat_id={uid} | text_preview={str(text)[:100]}")

# ---------- مساعد: استخراج مفتاح الموضوع بدون الايموجي ----------
def _topic_key(topic_text: str) -> str:
    if not topic_text:
        return ""
    parts = topic_text.split()
    return parts[-1] if parts else topic_text

# ---------- /start: بداية مسار التسجيل بالترتيب (اسم -> جنس -> عمر) ----------
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    print(f"[START] user={uid}")

    # رسالة ترحيب عشوائية (من messages.get_welcome_message)
    safe_send(uid, get_welcome_message("START"), reply_markup=ReplyKeyboardRemove())

    # ابدأ عملية التسجيل: نطلب الاسم أولاً
    update_user(uid, {"state": STATE_REGISTER_NAME})
    safe_send(uid, "✏️ ما اسمك؟ (أدخل الاسم من لوحة الكتابة)", reply_markup=ReplyKeyboardRemove())

# ---------- /help ----------
@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    if users[uid].get("banned_full"):
        return
    safe_send(uid, HELP, reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))

# ---------- ping للاختبار ----------
@bot.message_handler(commands=["ping"])
def cmd_ping(m: Message):
    try:
        cid = m.chat.id
        print(f"[DEBUG] ping from {cid}")
        bot.send_message(cid, "pong")
    except Exception as e:
        print(f"[ERROR] ping handler: {e}")

# ---------- معالجة الرسائل النصية العامة وتوجيه الحالات ----------
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return

    state = u.get("state") or ""
    print(f"[MSG] from={uid} state={state} text={txt[:50]}")

    # حالات التسجيل (الأساسية)
    if state == STATE_REGISTER_NAME:
        handle_register_name(uid, txt); return
    if state == STATE_REGISTER_GENDER:
        handle_register_gender(uid, txt); return
    if state == STATE_REGISTER_AGE:
        handle_register_age(uid, txt); return

    # حالات التعديل (اسم / عمر)
    if state == STATE_EDIT_NAME:
        handle_edit_name(uid, txt); return
    if state == STATE_EDIT_AGE:
        handle_edit_age(uid, txt); return

    # حالات التطبيق العادية
    if state == STATE_CHOOSE_TOPIC:
        handle_topic_selection(uid, txt); return
    if state == STATE_CHOOSE_TARGET_GENDER:
        handle_target_gender(uid, txt); return
    if state == STATE_CONFIRM_LEAVE:
        handle_leave_confirm(uid, u, txt); return
    if state == STATE_CONFIRM_REPORT:
        handle_report_text_confirm(uid, u, txt); return

    # أوامر من القائمة الرئيسية
    if txt == "👤 ملفي":
        safe_send(uid, profile_text(u), reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "✏️ تعديل الاسم":
        update_user(uid, {"state": STATE_EDIT_NAME})
        safe_send(uid, "✏️ أرسل الاسم الجديد:", reply_markup=ReplyKeyboardRemove())
        return

    if txt == "🎂 تعديل العمر":
        update_user(uid, {"state": STATE_EDIT_AGE})
        safe_send(uid, "🎂 أرسل العمر الجديد (10–120):", reply_markup=ReplyKeyboardRemove())
        return

    if txt == "🆘 مساعدة":
        safe_send(uid, HELP, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "🔍 البحث عن دردشة":
        handle_search_request(uid); return

    # إن كان في دردشة، مرّر الرسائل للشريك
    if u.get("partner"):
        handle_chat_message(uid, txt, u); return

    # افتراضي
    safe_send(uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", reply_markup=main_menu(in_chat=False))

# ---------- دوال التسجيل خطوة بخطوة ----------
def handle_register_name(uid, txt):
    # استخدام sanitize_name من Profile_manger
    name = sanitize_name(txt)
    if not name:
        safe_send(uid, "❌ الاسم غير صالح. استخدم 2–30 حرفًا (حروف ومسافات فقط). حاول مرة أخرى:")
        return
    # حفظ الاسم والتحول لانتظار الجنس
    update_user(uid, {"name": name, "state": STATE_REGISTER_GENDER})
    safe_send(uid, f"✅ تم حفظ الاسم: {name}")

    # اسأل عن الجنس مع كيبورد اختياري
    safe_send(uid, "💡 اختر جنسك (مرة واحدة):", reply_markup=gender_menu())

def handle_register_gender(uid, txt):
    txt = txt.strip()
    if txt not in getattr(config, "GENDERS", ["ذكر", "أنثى"]):
        safe_send(uid, "❌ اختر: ذكر / أنثى", reply_markup=gender_menu())
        return
    update_user(uid, {"gender": txt, "state": STATE_REGISTER_AGE})
    safe_send(uid, f"✅ تم حفظ الجنس: {txt}")
    # اسأل عن العمر (لوحة الكتابة)
    safe_send(uid, "🎂 ما عمرك؟ (10–120)", reply_markup=ReplyKeyboardRemove())

def handle_register_age(uid, txt):
    age = sanitize_age(txt)
    if not age:
        safe_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120:")
        return
    update_user(uid, {"age": age, "state": None})
    safe_send(uid, f"✅ تم حفظ العمر: {age}")

    # التسجيل اكتمل — أعرض القائمة الرئيسية
    safe_send(uid, "🎉 تم إعداد ملفك الشخصي بنجاح! يمكنك الآن استخدام القائمة:", reply_markup=main_menu(in_chat=False))

# ---------- دوال التعديل (الاسم/العمر) ----------
def handle_edit_name(uid, txt):
    name = sanitize_name(txt)
    if not name:
        safe_send(uid, "❌ الاسم غير صالح. حاول مجددًا:")
        return
    update_user(uid, {"name": name, "state": None})
    safe_send(uid, f"✅ تم تحديث الاسم إلى: {name}", reply_markup=main_menu(in_chat=False))

def handle_edit_age(uid, txt):
    age = sanitize_age(txt)
    if not age:
        safe_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120:")
        return
    update_user(uid, {"age": age, "state": None})
    safe_send(uid, f"✅ تم تحديث العمر إلى: {age}", reply_markup=main_menu(in_chat=False))

# ---------- بدء البحث عن دردشة ----------
def handle_search_request(uid):
    ensure_user(uid)
    u = users[uid]
    if u.get("partner"):
        safe_send(uid, "⚠️ أنت بالفعل في دردشة!", reply_markup=main_menu(in_chat=True))
        return
    update_user(uid, {"state": STATE_CHOOSE_TOPIC})
    safe_send(uid, "اختر موضوع النقاش:", reply_markup=topics_menu())

# ---------- اختيار موضوع -->
def handle_topic_selection(uid, txt):
    txt = txt.strip()
    if txt not in config.TOPICS:
        safe_send(uid, "❌ اختر موضوعًا صالحًا من القائمة.", reply_markup=topics_menu())
        return
    update_user(uid, {"topic": txt, "state": STATE_CHOOSE_TARGET_GENDER})
    safe_send(uid, f"تم اختيار الموضوع: {txt}\nالآن اختر جنس الطرف الذي تريده:", reply_markup=target_gender_menu())

# ---------- اختيار جنس الشريك -->
def handle_target_gender(uid, txt):
    txt = txt.strip()
    valid = getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"])
    if txt not in valid:
        safe_send(uid, f"❌ اختر: {' / '.join(valid)}", reply_markup=target_gender_menu())
        return

    # تحويل لتمثيل داخلي
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
    safe_send(uid, get_welcome_message(_topic_key(topic)))
    safe_send(uid, SEARCHING, reply_markup=main_menu(in_chat=False))

    # أضف إلى الانتظار وجرب المطابقة
    try:
        add_to_wait(topic, uid, target)  # ملاحظة: توقّع واجهة add_to_wait(topic, uid, target) أو (uid, topic, target) حسب ملف matchmaking.py لديك
    except Exception:
        # دعم واجهات محتملة قديمة
        try:
            add_to_wait(uid, topic, target)
        except Exception as e:
            print(f"[add_to_wait ERROR] {e}")

    # حاول المطابقة (try_match قد تختلف الواجهة)
    partner = None
    try:
        partner = try_match(uid, topic)
    except Exception:
        try:
            partner = try_match(uid, topic, target)
        except Exception as e:
            print(f"[try_match ERROR] {e}")

    if partner:
        try:
            pid = int(partner)
            update_user(uid, {"partner": pid, "state": None, "chat_started_at": time.time()})
            update_user(pid, {"partner": uid, "state": None, "chat_started_at": time.time()})
            try:
                start_history(uid); start_history(pid)
            except Exception:
                pass
            safe_send(uid, INTRO_PARTNER, reply_markup=main_menu(in_chat=True))
            try:
                safe_send(pid, INTRO_PARTNER, reply_markup=main_menu(in_chat=True))
            except Exception:
                pass
        except Exception as e:
            print(f"[MATCH SETUP ERROR] {e}")

    # شغّل ووتشر للتايم آوت إن وُجد
    try:
        start_timeout_watcher(bot)
    except Exception:
        try:
            start_timeout_watcher()
        except Exception as e:
            print(f"[start_timeout_watcher ERROR] {e}")

# ---------- مغادرة الدردشة ----------
def handle_leave_request(uid):
    ensure_user(uid)
    u = users[uid]
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    if elapsed < getattr(config, "LEAVE_DELAY", 30):
        safe_send(uid, LEAVE_TOO_SOON.format(remain=int(getattr(config, "LEAVE_DELAY", 30) - elapsed)))
        return
    update_user(uid, {"state": STATE_CONFIRM_LEAVE})
    safe_send(uid, LEAVE_CONFIRM, reply_markup=yes_no_menu())

def handle_leave_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        if pid:
            try:
                end_session(uid, pid)
            except Exception:
                try:
                    end_session(u, users.get(pid))
                except Exception:
                    pass
            update_user(uid, {"partner": None, "state": None, "chat_started_at": None})
            update_user(pid, {"partner": None, "state": None, "chat_started_at": None})
            safe_send(uid, "لقد غادرت الدردشة.", reply_markup=main_menu(in_chat=False))
            try:
                safe_send(pid, "شريكك غادر الدردشة.", reply_markup=main_menu(in_chat=False))
            except Exception:
                pass
        else:
            update_user(uid, {"state": None})
            safe_send(uid, "لم يتم العثور على شريك حالي.")
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_send(uid, "تم الإلغاء. تابع الدردشة 👌")
    else:
        safe_send(uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())

# ---------- تبسيط تأكيد الإبلاغ (نص) ----------
def handle_report_text_confirm(uid, u, txt):
    # هذا المسار يستخدم عندما نطلب تأكيدًا نصيًا (نحو إمكانية توافُر callback_query لاحقًا)
    if txt == "نعم ✅":
        pid = u.get("partner")
        try:
            result = review_history_and_penalize(uid, pid, u.get("history", []))
        except Exception as e:
            print(f"[review_history_and_penalize ERROR] {e}")
            result = None
        update_user(uid, {"state": None})
        safe_send(uid, REPORT_OK)
        if result:
            safe_send(uid, REPORT_RESULT.format(lines=result[0], respect=u.get("respect", "—")))
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_send(uid, "تم الإلغاء. شكراً لحرصك.")
    else:
        safe_send(uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())
        return

    # بعدها نعرض زر "مغادرة" دائماً لتجنب تعليق الأزرار
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🚪 مغادرة الدردشة"))
    safe_send(uid, "هل تريد الآن مغادرة الدردشة؟", reply_markup=kb)

# ---------- تمرير الرسائل بين الشركاء ----------
def handle_chat_message(uid, txt, u):
    if is_muted(uid):
        safe_send(uid, MUTED.format(left=60))
        return

    try:
        if contains_bad_word(txt):
            txt_to_send = censor_text(txt)
            safe_send(uid, "⚠️ تم تعديل رسالتك لاحتوائها على كلمات غير لائقة.")
        else:
            txt_to_send = txt
    except Exception:
        txt_to_send = txt

    try:
        apply_respect(uid, txt_to_send)
    except Exception:
        pass

    try:
        append_history(uid, txt_to_send)
    except Exception:
        pass

    pid = u.get("partner")
    if not pid or pid not in users:
        update_user(uid, {"partner": None})
        safe_send(uid, "لا يوجد شريك حالي — عد إلى القائمة.", reply_markup=main_menu(in_chat=False))
        return

    try:
        bot.send_message(pid, f"💬 {txt_to_send}")
    except Exception as e:
        print(f"[SEND TO PARTNER ERROR] {e}")
        safe_send(uid, "حدث خطأ أثناء إرسال الرسالة إلى الشريك.")

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

# ---------- تهيئة watcher إن وُجد ----------
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
