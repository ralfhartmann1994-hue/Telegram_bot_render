# Main.py
import os
import time
import traceback
import telebot
from flask import Flask, request
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message

# ---------- استدعاء الإعدادات والملفات المساندة ----------
import config  # يجب أن يحتوي على TOKEN, WEBHOOK_URL, WEBHOOK_PATH, PORT, LEAVE_DELAY, TOPICS, GENDERS, TARGET_GENDERS
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
# Bad_word helper (إن وُجد) لتصفية الكلمات السيئة — إذا لم تكن موجودة عدّل الاستدعاء أو أنشئ دوال مماثلة
try:
    from Bad_word import contains_bad_word, censor_text
except Exception:
    # نُعرّف نواتج افتراضية إذا لم يكن الملف موجودًا بالاسم ذاته
    def contains_bad_word(text):
        return False

    def censor_text(text):
        return text

# ---------- إنشاء البوت وفلَسْك ----------
TOKEN = getattr(config, "TOKEN", None)
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN مفقود. ضعه في config.TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ---------- مساعدة: قائمة رئيسية وكيبوردات ----------
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
    kb.add(KeyboardButton("👨 رجل"), KeyboardButton("👩 امرأة"))
    kb.add(KeyboardButton("أي"))
    return kb

def yes_no_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# ---------- تحديث مستخدم آمن + تحميل سابق ----------
def update_user(uid, updates: dict):
    ensure_user(uid)
    users[uid].update(updates)
    try:
        save_users()
    except Exception as e:
        print(f"[SAVE USER ERROR] {e}")

# تحميل المستخدمين عند الإقلاع
load_users()

# ---------- دوال مساعدة متعلقة بالحالات ----------
def safe_delayed_send(uid, text, delay=0.4, **kwargs):
    try:
        delayed_send(bot, uid, text, delay=delay, **kwargs)
    except Exception as e:
        print(f"[DELAYED_SEND ERROR] {e}, text: {text}")

# ---------- /start ----------
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]

    if u.get("banned_full"):
        delayed_send(bot, uid, BANNED, delay=0.4)
        return

    # ---- إرسال رسالة البداية العشوائية من START_MESSAGES ----
    welcome_text = get_welcome_message(topic="START")
    delayed_send(bot, uid, welcome_text, delay=0.4, reply_markup=ReplyKeyboardRemove())

    # ---- إذا المستخدم جديد ولم يحدد الجنس ----
    if not u.get("gender"):
        u["state"] = "AWAIT_GENDER"
        save_users()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(*[KeyboardButton(g) for g in config.GENDERS])
        delayed_send(bot, uid, "اختر جنسًا (مرة واحدة فقط):", delay=0.8, reply_markup=kb)
        return

    # ---- مستخدم عائد ----
    u["state"] = None
    save_users()
    delayed_send(
        bot,
        uid,
        "مرحبًا من جديد! اختر من القائمة:",
        delay=0.4,
        reply_markup=main_menu(in_chat=bool(u.get("partner")))
    )

# ---------- /help ----------
@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    if users[uid].get("banned_full"):
        return
    safe_delayed_send(uid, HELP, delay=0.2, reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))


# ---------- معالجة نصية عامة (التحقق من الحالات والأزرار) ----------
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return

    # الحالة الحالية
    state = u.get("state") or ""

    # حالات انتظار بناءة
    if state == "AWAIT_GENDER":
        handle_gender(uid, txt); return
    if state == "AWAIT_NAME":
        handle_edit_name(uid, txt); return
    if state == "AWAIT_AGE":
        handle_edit_age(uid, txt); return
    if state == "CHOOSE_TOPIC":
        handle_topic_selection(uid, txt); return
    if state == "CHOOSE_TARGET_GENDER":
        handle_target_gender(uid, txt); return
    if state == "CONFIRM_LEAVE":
        handle_leave_confirm(uid, u, txt); return
    if state == "CONFIRM_REPORT":
        handle_report_confirm(uid, u, txt); return

    # أوامر أزرار ثابتة
    if txt == "👤 ملفي":
        safe_delayed_send(uid, profile_text(u), delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "✏️ تعديل الاسم":
        update_user(uid, {"state": "AWAIT_NAME"})
        safe_delayed_send(uid, "أدخل الاسم الجديد:", delay=0.2, reply_markup=ReplyKeyboardRemove())
        return

    if txt == "🎂 تعديل العمر":
        update_user(uid, {"state": "AWAIT_AGE"})
        safe_delayed_send(uid, "أدخل العمر الجديد (10–120):", delay=0.2, reply_markup=ReplyKeyboardRemove())
        return

    if txt == "🆘 مساعدة":
        safe_delayed_send(uid, HELP, delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "🔍 البحث عن دردشة":
        handle_search_request(uid); return

    # عند وجود شريك، تُمرر الرسائل له (بعد فلاتر ومرشحات)
    if u.get("partner"):
        handle_chat_message(uid, txt, u); return

    # Default
    safe_delayed_send(uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", delay=0.2, reply_markup=main_menu(in_chat=False))


# ---------- معالجة الجنس ----------
def handle_gender(uid, txt):
    txt = txt.strip()
    if txt not in getattr(config, "GENDERS", ["ذكر", "أنثى", "أخرى"]):
        safe_delayed_send(uid, "اختر: ذكر / أنثى / أخرى", delay=0.2)
        return
    update_user(uid, {"gender": txt, "state": None})
    safe_delayed_send(uid, "تم حفظ الجنس ✅", delay=0.2, reply_markup=main_menu(in_chat=False))


# ---------- تعديل الاسم ----------
def handle_edit_name(uid, txt):
    name = sanitize_name(txt)
    update_user(uid, {"name": name, "state": None})
    safe_delayed_send(uid, f"✅ تم تحديث الاسم إلى: {name}", delay=0.2, reply_markup=main_menu(in_chat=False))


# ---------- تعديل العمر ----------
def handle_edit_age(uid, txt):
    age = sanitize_age(txt)
    if not age:
        safe_delayed_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120.", delay=0.2, reply_markup=ReplyKeyboardRemove())
        return
    update_user(uid, {"age": age, "state": None})
    safe_delayed_send(uid, f"✅ تم تحديث العمر إلى: {age}", delay=0.2, reply_markup=main_menu(in_chat=False))


# ---------- بدء البحث عن دردشة (موضوع + اختيار الجنس المستهدف) ----------
def handle_search_request(uid):
    ensure_user(uid)
    u = users[uid]
    if u.get("partner"):
        safe_delayed_send(uid, "⚠️ أنت بالفعل في دردشة!", delay=0.2)
        return

    update_user(uid, {"state": "CHOOSE_TOPIC"})
    kb = topics_menu()
    safe_delayed_send(uid, "اختر موضوع النقاش:", delay=0.2, reply_markup=kb)


# ---------- اختيار الموضوع ثم اختيار التارجت جندر ثم بدء البحث ----------
def handle_topic_selection(uid, txt):
    txt = txt.strip()
    if txt not in config.TOPICS:
        safe_delayed_send(uid, "❌ اختر موضوعًا صالحًا من القائمة.", delay=0.2, reply_markup=topics_menu())
        return

    update_user(uid, {"topic": txt, "state": "CHOOSE_TARGET_GENDER"})
    safe_delayed_send(uid, f"تم اختيار الموضوع: {txt}\nالآن اختر جنس الطرف الذي تريده:", delay=0.2, reply_markup=target_gender_menu())


def handle_target_gender(uid, txt):
    txt = txt.strip()
    valid = ["👨 رجل", "👩 امرأة", "أي"]
    if txt not in valid:
        safe_delayed_send(uid, "❌ اختر: 👨 رجل / 👩 امرأة / أي", delay=0.2, reply_markup=target_gender_menu())
        return

    # حفظ الإعداد والبدء بالبحث
    # نحول الاختيارات إلى قيمة قابلة للمعالجة
    target = None
    if txt == "👨 رجل":
        target = "male"
    elif txt == "👩 امرأة":
        target = "female"
    else:
        target = "any"

    u = users[uid]
    topic = u.get("topic")
    update_user(uid, {"target_gender": target, "state": "SEARCHING"})
    # إرسال رسالة ترحيب خاصة للموضوع المختار
    safe_delayed_send(uid, get_welcome_message(topic), delay=0.4)
    safe_delayed_send(uid, SEARCHING, delay=0.4, reply_markup=main_menu(in_chat=False))

    # أضف المستخدم إلى قائمة الانتظار بحسب Matchmaking
    try:
        add_to_wait(uid, topic, target)
    except TypeError:
        # إذا كانت واجهة add_to_wait قد تختلف، نعمل بديل بسيط:
        try:
            add_to_wait(uid, topic)
        except Exception as e:
            print(f"[add_to_wait ERROR] {e}")

    # جرب المطابقة
    try:
        try_match(bot, uid, topic, target)
    except TypeError:
        try:
            try_match(bot, uid, topic)
        except Exception as e:
            print(f"[try_match ERROR] {e}")

    # شغّل ووتشر للتايم آوت لو كان دالة منفصلة في Matchmaking
    try:
        start_timeout_watcher(bot, uid, topic)
    except TypeError:
        try:
            start_timeout_watcher(bot)
        except Exception as e:
            print(f"[start_timeout_watcher ERROR] {e}")


# ---------- معالجة مغادرة الدردشة (تأكيد ومغادرة) ----------
def handle_leave_request(uid):
    ensure_user(uid)
    u = users[uid]
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    if elapsed < getattr(config, "LEAVE_DELAY", 30):
        safe_delayed_send(uid, LEAVE_TOO_SOON.format(remain=int(getattr(config, "LEAVE_DELAY", 30) - elapsed)), delay=0.2)
        return
    update_user(uid, {"state": "CONFIRM_LEAVE"})
    safe_delayed_send(uid, LEAVE_CONFIRM, delay=0.2, reply_markup=yes_no_menu())


def handle_leave_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        if pid:
            # إنهاء الجلسة لكليهما باستخدام Profile_manger.end_session أو دالة معادلة
            try:
                end_session(u, users.get(pid))
            except Exception:
                # محاولة بديلة: استدعاء end_session على اليوزر ids
                try:
                    end_session(uid)
                    end_session(pid)
                except Exception as e:
                    print(f"[END_SESSION ERROR] {e}")
            # تحديث الحقول محليًا
            update_user(uid, {"partner": None, "state": None})
            update_user(pid, {"partner": None, "state": None})
            safe_delayed_send(uid, "لقد غادرت الدردشة.", delay=0.2, reply_markup=main_menu(in_chat=False))
            try:
                safe_delayed_send(pid, "شريكك غادر الدردشة.", delay=0.2, reply_markup=main_menu(in_chat=False))
            except Exception:
                pass
        else:
            update_user(uid, {"state": None})
            safe_delayed_send(uid, "لم يتم العثور على شريك حالي.", delay=0.2)
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_delayed_send(uid, "تم الإلغاء. تابع الدردشة 👌", delay=0.2)
    else:
        safe_delayed_send(uid, "اختر: نعم ✅ / لا ❌", delay=0.2, reply_markup=yes_no_menu())


# ---------- الإبلاغ عن شريك (تأكيد ثم مراجعة) ----------
def handle_report_request(uid):
    ensure_user(uid)
    u = users[uid]
    if not u.get("partner"):
        safe_delayed_send(uid, "❌ أنت لست في دردشة الآن.", delay=0.2)
        return
    update_user(uid, {"state": "CONFIRM_REPORT"})
    safe_delayed_send(uid, REPORT_CONFIRM, delay=0.2, reply_markup=yes_no_menu())


def handle_report_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        # اطلب من نظام المودريشن مراجعة الرسائل
        try:
            result = review_history_and_penalize(uid, pid)  # من Moderation.py
        except Exception as e:
            print(f"[review_history_and_penalize ERROR] {e}")
            result = None
        update_user(uid, {"state": None})
        safe_delayed_send(uid, REPORT_OK, delay=0.2)
        if result:
            # إرسال نتيجة مبدئية إن كانت الدالة تعيد شيئًا
            try:
                safe_delayed_send(uid, REPORT_RESULT.format(lines=result.get("lines", "—"), respect=result.get("respect", "—")), delay=0.4)
            except Exception:
                pass
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_delayed_send(uid, "تم الإلغاء. شكراً لحرصك.", delay=0.2)
    else:
        safe_delayed_send(uid, "اختر: نعم ✅ / لا ❌", delay=0.2, reply_markup=yes_no_menu())


# ---------- تمرير الرسائل بين الشركاء مع فلترة ومودريشن بسيطة ----------
def handle_chat_message(uid, txt, u):
    # تحقق إن المستخدم موقوف مؤقتًا
    if is_muted(uid):
        # is_muted يمكن أن تُرجع وقت متبقي أو boolean — نحن ندعم boolean هنا
        safe_delayed_send(uid, MUTED.format(left=60), delay=0.2)
        return

    # فلترة كلمات سيئة إذا كانت الدالة موجودة
    try:
        if contains_bad_word(txt):
            censored = censor_text(txt)
            safe_delayed_send(uid, "⚠️ تم تعديل رسالتك لاحتوائها على كلمات غير لائقة.", delay=0.2)
            txt_to_send = censored
        else:
            txt_to_send = txt
    except Exception:
        txt_to_send = txt

    # تطبيق نظام الاحترام (زيادة/نقصان نقاط مثلاً)
    try:
        apply_respect(uid, txt_to_send)
    except Exception:
        pass

    # حفظ السجل (Profile_manger.append_history)
    try:
        append_history(uid, txt_to_send)
    except Exception:
        pass

    # إرسال الرسالة للشريك
    pid = u.get("partner")
    if not pid or pid not in users:
        update_user(uid, {"partner": None})
        safe_delayed_send(uid, "لا يوجد شريك حالي — عد إلى القائمة.", delay=0.2, reply_markup=main_menu(in_chat=False))
        return

    try:
        bot.send_message(pid, f"💬 {txt_to_send}")
    except Exception as e:
        print(f"[SEND TO PARTNER ERROR] {e}")
        # إذا فشل الإرسال نعلم المرسل
        safe_delayed_send(uid, "حدث خطأ أثناء إرسال الرسالة إلى الشريك.", delay=0.2)


# ---------- Webhook: استقبال تحديثات من Telegram عبر Flask ----------
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


# ---------- تهيئة Matchmaking watcher لو كانت موجودة ----------
try:
    # إذا Matchmaking.start_timeout_watcher تتطلب bot فقط
    start_timeout_watcher(bot)
except Exception:
    try:
        start_timeout_watcher()
    except Exception:
        pass

# ---------- نقطة التشغيل الرئيسية ----------
if __name__ == "__main__":
    # تحميل المستخدمين مسبقًا
    try:
        load_users()
    except Exception as e:
        print(f"[LOAD_USERS ERROR] {e}")
    # إعداد webhook إذا موجود
    try:
        set_webhook()
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")

    # تشغيل Flask app (عند استخدام webhook)
    port = int(os.environ.get("PORT", getattr(config, "PORT", 5000)))
    print(f"[RUN] Webhook listening on port {port}…")
    app.run(host="0.0.0.0", port=port) 
