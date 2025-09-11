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

# Bad_word helper (إن وُجد) لتصفية الكلمات السيئة — إذا لم يكن الملف موجودًا عدّل الاستدعاء أو أنشئ دوال مماثلة
try:
    from Bad_word import contains_bad_word, censor_text
except Exception:
    def contains_bad_word(text):
        return False

    def censor_text(text):
        return text

# ---------- إنشاء البوت وفلَسْك ----------
TOKEN = getattr(config, "TOKEN", None) or os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN مفقود. ضعه في config.TOKEN أو كمتغير بيئة TELEGRAM_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ---------- ثوابت الحالات ----------
STATE_AWAIT_GENDER = "AWAIT_GENDER"
STATE_AWAIT_NAME = "AWAIT_NAME"
STATE_AWAIT_AGE = "AWAIT_AGE"
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

def target_gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    # نستخدم القيم كما في config.TARGET_GENDERS (المستخدم طلب فقط "رجل" و "امرأة")
    for tg in getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"]):
        kb.add(KeyboardButton(tg))
    return kb

def yes_no_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# ---------- تحميل/حفظ المستخدمين ----------
load_users()

# ---------- تحديث مستخدم آمن + حفظ ----------
def update_user(uid, updates: dict):
    ensure_user(uid)
    users[uid].update(updates)
    try:
        save_users()
    except Exception as e:
        print(f"[SAVE USER ERROR] {e}")

# ---------- غلاف إرسال آمن يدعم delay ---------- 
# (delayed_send موجود في messages.py ويقوم بالsleep ثم bot.send_message)
def safe_delayed_send(uid, text, delay=0.0, **kwargs):
    try:
        # delay افتراضي 0 لتكون الاستجابة فورية إلا عند الحاجة
        delayed_send(bot, uid, text, delay=delay, **kwargs)
    except TypeError as e:
        # في حال كانت دالة delayed_send مختلفة أو kwargs غير مناسبة
        print(f"[DELAYED_SEND TYPEERROR] {e}, trying direct send without delay")
        try:
            bot.send_message(uid, text, **{k:v for k,v in kwargs.items() if k != "delay"})
        except Exception as e2:
            print(f"[SEND_MESSAGE ERROR] {e2} | text: {text}")
    except Exception as e:
        print(f"[DELAYED_SEND ERROR] {e} | text: {text}")

# ---------- دوال مساعدة صغيرة ----------
def _topic_key(topic_text: str) -> str:
    """يحاول استخراج النص العربي (بدون الايموجي) من عنصر TOPICS مثل '⚽ رياضة' -> 'رياضة'"""
    if not topic_text:
        return ""
    parts = topic_text.split()
    return parts[-1] if parts else topic_text

# ---------- /start ----------
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    print(f"[START] user={uid}")

    # رسالة ترحيب
    safe_delayed_send(uid, get_welcome_message("START"), reply_markup=ReplyKeyboardRemove())

    # اسأل عن الاسم أولًا
    update_user(uid, {"state": STATE_AWAIT_NAME})
    safe_delayed_send(uid, "✏️ ما اسمك؟", reply_markup=ReplyKeyboardRemove())

# ---------- /help ----------
@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    if users[uid].get("banned_full"):
        return
    safe_delayed_send(uid, HELP, delay=0.0, reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))

# ---------- ping (اختبار) ----------
@bot.message_handler(commands=["ping"])
def cmd_ping(m: Message):
    try:
        cid = m.chat.id
        print(f"[DEBUG] ping from {cid}")
        bot.send_message(cid, "pong")
    except Exception as e:
        print(f"[ERROR] ping handler: {e}")

# ---------- المعالجة العامة للرسائل النصية ----------
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return

    state = u.get("state") or ""

    # حالات انتظـار
    if state == STATE_AWAIT_GENDER:
        handle_gender(uid, txt); return
    if state == STATE_AWAIT_NAME:
        handle_edit_name(uid, txt); return
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
    if state == STATE_AWAIT_NAME:
        handle_name_registration(uid, txt); return

    # أوامر أزرار ثابتة
    if txt == "👤 ملفي":
        safe_delayed_send(uid, profile_text(u), delay=0.0, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "✏️ تعديل الاسم":
        update_user(uid, {"state": STATE_AWAIT_NAME})
        safe_delayed_send(uid, "أدخل الاسم الجديد:", delay=0.0, reply_markup=ReplyKeyboardRemove())
        return

    if txt == "🎂 تعديل العمر":
        update_user(uid, {"state": STATE_AWAIT_AGE})
        safe_delayed_send(uid, "أدخل العمر الجديد (10–120):", delay=0.0, reply_markup=ReplyKeyboardRemove())
        return

    if txt == "🆘 مساعدة":
        safe_delayed_send(uid, HELP, delay=0.0, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "🔍 البحث عن دردشة":
        handle_search_request(uid); return

    # إذا المستخدم في دردشة (partner موجود)، فمرّر الرسائل للشريك
    if u.get("partner"):
        handle_chat_message(uid, txt, u); return

    # Default
    safe_delayed_send(uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", delay=0.0, reply_markup=main_menu(in_chat=False))

# ---------- معالجة اختيار الجنس ----------
def handle_gender(uid, txt):
    txt = txt.strip()
    if txt not in config.GENDERS:
        delayed_send(bot, uid, "❌ اختر: ذكر / أنثى", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(*[KeyboardButton(g) for g in config.GENDERS]))
        return

    update_user(uid, {"gender": txt, "state": STATE_AWAIT_AGE})
safe_delayed_send(uid, f"✅ تم حفظ الجنس: {txt}")

# اسأل عن العمر بعد اختيار الجنس
safe_delayed_send(uid, "🎂 ما عمرك؟ (10–120)", reply_markup=ReplyKeyboardRemove())

    # بعد الحفظ: وجه المستخدم لبدء البحث أو اختيار الموضوع إذا أردت فوراً
    # مثال: نتركه يضغط 🔍 البحث عن دردشة من القائمة
    delayed_send(bot, uid, "يمكنك الآن الضغط على 🔍 البحث عن دردشة لبدء.", reply_markup=main_menu(in_chat=False))

#-------- معالجة الاسم -----------
def handle_name_registration(uid, txt):
    name = sanitize_name(txt)
    if not (2 <= len(name) <= 30):
        safe_delayed_send(uid, "❌ الاسم غير صالح، حاول مجددًا:")
        return
    update_user(uid, {"name": name, "state": STATE_AWAIT_GENDER})

    # اسأل عن الجنس مع أزرار
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(*[KeyboardButton(g) for g in config.GENDERS])
    safe_delayed_send(uid, "💡 اختر جنسك:", reply_markup=kb) 

# ---------- تعديل الاسم ----------
def handle_edit_name(uid, txt):
    name = sanitize_name(txt)
    update_user(uid, {"name": name, "state": None})
    safe_delayed_send(uid, f"✅ تم تحديث الاسم إلى: {name}", delay=0.0, reply_markup=main_menu(in_chat=False))

# ---------- تعديل العمر ----------
def handle_edit_age(uid, txt):
    age = sanitize_age(txt)
    if not age:
        safe_delayed_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120.", delay=0.0, reply_markup=ReplyKeyboardRemove())
        return
    update_user(uid, {"age": age, "state": None})
    safe_delayed_send(uid, f"✅ تم تحديث العمر إلى: {age}", delay=0.0, reply_markup=main_menu(in_chat=False))

# ---------- بدء البحث عن دردشة (يعرض قائمة المواضيع) ----------
def handle_search_request(uid):
    ensure_user(uid)
    u = users[uid]
    if u.get("partner"):
        safe_delayed_send(uid, "⚠️ أنت بالفعل في دردشة!", delay=0.0)
        return
    update_user(uid, {"state": STATE_CHOOSE_TOPIC})
    safe_delayed_send(uid, "اختر موضوع النقاش:", delay=0.0, reply_markup=topics_menu())

# ---------- اختيار الموضوع ----------
def handle_topic_selection(uid, txt):
    txt = txt.strip()
    if txt not in config.TOPICS:
        safe_delayed_send(uid, "❌ اختر موضوعًا صالحًا من القائمة.", delay=0.0, reply_markup=topics_menu())
        return
    update_user(uid, {"topic": txt, "state": STATE_CHOOSE_TARGET_GENDER})
    safe_delayed_send(uid, f"تم اختيار الموضوع: {txt}\nالآن اختر جنس الطرف الذي تريده:", delay=0.0, reply_markup=target_gender_menu())

# ---------- اختيار جنس الشريك وبدء البحث ----------
def handle_target_gender(uid, txt):
    txt = txt.strip()
    valid = getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"])
    if txt not in valid:
        safe_delayed_send(uid, f"❌ اختر: {' / '.join(valid)}", delay=0.0, reply_markup=target_gender_menu())
        return

    # تحويل الواجهة إلى قيمة منطقية
    if "رجل" in txt:
        target = "male"
    elif "امرأة" in txt or "امرأ" in txt:
        target = "female"
    else:
        target = "any"

    u = users[uid]
    topic = u.get("topic")
    update_user(uid, {"target_gender": target, "state": STATE_SEARCHING})

    # رسالة ترحيب خاصة للموضوع (نمرّر المفتاح بدون الايموجي)
    topic_key = _topic_key(topic)
    safe_delayed_send(uid, get_welcome_message(topic_key), delay=0.0)

    # نعلم المستخدم أننا نبحث
    safe_delayed_send(uid, SEARCHING, delay=0.0, reply_markup=main_menu(in_chat=False))

    # أضف المستخدم إلى قائمة الانتظار بحسب Matchmaking — دعنا ندعم عدة تواقيع
    try:
        add_to_wait(uid, topic, target)
    except TypeError:
        try:
            add_to_wait(uid, topic)
        except Exception as e:
            print(f"[add_to_wait ERROR] {e}")

    # حاول المطابقة — جرب الواجهات الممكنة
    partner = None
    try:
        partner = try_match(uid, topic, target)
    except TypeError:
        try:
            partner = try_match(bot, uid, topic, target)
        except Exception as e:
            print(f"[try_match ERROR] {e}")
    except Exception as e:
        print(f"[try_match ERROR] {e}")

    # إذا try_match أرجعت شريك (id) فنقوم بتهيئة الدردشة محليًا
    if partner:
        try:
            pid = int(partner)
            # وحدّث الطرفين محليًا (بعض Matchmaking قد يفعل هذا داخليًا)
            update_user(uid, {"partner": pid, "state": None, "chat_started_at": time.time()})
            update_user(pid, {"partner": uid, "state": None, "chat_started_at": time.time()})
            # بدء التاريخ إن وُجدت الدالة
            try:
                start_history(uid); start_history(pid)
            except Exception:
                pass
            safe_delayed_send(uid, INTRO_PARTNER, delay=0.0, reply_markup=main_menu(in_chat=True))
            try:
                safe_delayed_send(pid, INTRO_PARTNER, delay=0.0, reply_markup=main_menu(in_chat=True))
            except Exception:
                pass
        except Exception as e:
            print(f"[MATCH SETUP ERROR] {e}")

    # شغّل ووتشر للتايم آوت (إن وُجد)
    try:
        start_timeout_watcher(bot, uid, topic)
    except TypeError:
        try:
            start_timeout_watcher(bot)
        except Exception as e:
            print(f"[start_timeout_watcher ERROR] {e}")

# ---------- مغادرة الدردشة ----------
def handle_leave_request(uid):
    ensure_user(uid)
    u = users[uid]
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    if elapsed < getattr(config, "LEAVE_DELAY", 30):
        safe_delayed_send(uid, LEAVE_TOO_SOON.format(remain=int(getattr(config, "LEAVE_DELAY", 30) - elapsed)), delay=0.0)
        return
    update_user(uid, {"state": STATE_CONFIRM_LEAVE})
    safe_delayed_send(uid, LEAVE_CONFIRM, delay=0.0, reply_markup=yes_no_menu())

def handle_leave_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        if pid:
            # نافذة إنهاء الجلسة عبر Profile_manger.end_session أو دوال بديلة
            try:
                end_session(uid, pid)  # أفضل شكل إن كانت الدالة تعمل على ids
            except TypeError:
                try:
                    end_session(u, users.get(pid))
                except Exception:
                    try:
                        end_session(uid)
                        end_session(pid)
                    except Exception as e:
                        print(f"[END_SESSION ERROR] {e}")
            # تنظيف الحقول
            update_user(uid, {"partner": None, "state": None, "chat_started_at": None})
            update_user(pid, {"partner": None, "state": None, "chat_started_at": None})
            safe_delayed_send(uid, "لقد غادرت الدردشة.", delay=0.0, reply_markup=main_menu(in_chat=False))
            try:
                safe_delayed_send(pid, "شريكك غادر الدردشة.", delay=0.0, reply_markup=main_menu(in_chat=False))
            except Exception:
                pass
        else:
            update_user(uid, {"state": None})
            safe_delayed_send(uid, "لم يتم العثور على شريك حالي.", delay=0.0)
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        safe_delayed_send(uid, "تم الإلغاء. تابع الدردشة 👌", delay=0.0)
    else:
        safe_delayed_send(uid, "اختر: نعم ✅ / لا ❌", delay=0.0, reply_markup=yes_no_menu())

# ---------- الإبلاغ ----------
@bot.callback_query_handler(func=lambda c: c.data in ["report_yes", "report_no"])
def handle_report_confirm(uid, u, txt):
    if txt == "نعم ✅":
        pid = u.get("partner")
        try:
            result = review_history_and_penalize(uid, pid, u.get("history", []))
        except Exception as e:
            print(f"[review_history_and_penalize ERROR] {e}")
            result = None
        update_user(uid, {"state": None})
        delayed_send(bot, uid, REPORT_OK)
        if result:
            delayed_send(bot, uid, REPORT_RESULT.format(lines=result[0], respect=u.get("respect", "—")))
    elif txt == "لا ❌":
        update_user(uid, {"state": None})
        delayed_send(bot, uid, "تم الإلغاء. شكراً لحرصك.")
    else:
        delayed_send(bot, uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())
        return

    # بعدها أرسل زر المغادرة دائماً
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🚪 مغادرة الدردشة"))
    delayed_send(bot, uid, "هل تريد الآن مغادرة الدردشة؟", reply_markup=kb)

# ---------- تمرير الرسائل بين الشركاء ----------
def handle_chat_message(uid, txt, u):
    # تأكد من عدم حظر المستخدم
    if is_muted(uid):
        safe_delayed_send(uid, MUTED.format(left=60), delay=0.0)
        return

    # فلترة كلمات سيئة
    try:
        if contains_bad_word(txt):
            txt_to_send = censor_text(txt)
            safe_delayed_send(uid, "⚠️ تم تعديل رسالتك لاحتوائها على كلمات غير لائقة.", delay=0.0)
        else:
            txt_to_send = txt
    except Exception:
        txt_to_send = txt

    # تطبيق نظام الاحترام
    try:
        apply_respect(uid, txt_to_send)
    except Exception:
        pass

    # حفظ السجل
    try:
        append_history(uid, txt_to_send)
    except Exception:
        pass

    # ارسال الشريك
    pid = u.get("partner")
    if not pid or pid not in users:
        update_user(uid, {"partner": None})
        safe_delayed_send(uid, "لا يوجد شريك حالي — عد إلى القائمة.", delay=0.0, reply_markup=main_menu(in_chat=False))
        return

    try:
        bot.send_message(pid, f"💬 {txt_to_send}")
    except Exception as e:
        print(f"[SEND TO PARTNER ERROR] {e}")
        safe_delayed_send(uid, "حدث خطأ أثناء إرسال الرسالة إلى الشريك.", delay=0.0)

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
