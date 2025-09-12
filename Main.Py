# Main.py
# ملف أساسي لبوت تيليجرام: تكامل مع profile.py, storage.py, Matchmaking.py, Moderation.py, messages.py, Bad_word.py
# يوفّر تسلسلاً واضحاً: /start -> (اسم -> جنس -> عمر) -> قائمة رئيسية -> البحث / الدردشة
# تاريخ: 2025

import os
import time
import traceback
from typing import Optional

from flask import Flask, request
import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    Message,
)

# ---------- استيراد ملفات المشروع ----------
# ملف التخزين (يحتوي على dict users، ودوال load_users/save_users/ensure_user إن وُجدت)
import storage
from storage import users, load_users, save_users, ensure_user as storage_ensure_user

# ملف إدارة البروفايل (النسخة التي طلبتَها)
import Profile_manger as ProfileManager
from Profile_manger import (
    ensure_user,
    set_user_name,
    set_user_age,
    set_user_gender,
    profile_text,
    start_history,
    append_history,
    end_session,
)

# Matchmaking (انتظار ومطابقة وإدارة الوقت)
try:
    from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
except Exception:
    # واجهات بديلة / استبدال تجريبي
    def add_to_wait(*args, **kwargs):
        raise RuntimeError("Matchmaking.add_to_wait غير متاح")
    def try_match(*args, **kwargs):
        return None
    def start_timeout_watcher(bot=None):
        return
    def remove_from_wait(*args, **kwargs):
        return

# Moderation (فلاتر كلمات، ميوت، احترام)
try:
    from Moderation import is_muted, apply_respect, review_history_and_penalize, check_message_safe
except Exception:
    def is_muted(uid): return False
    def apply_respect(uid, text): return
    def review_history_and_penalize(uid, pid, history): return None
    def check_message_safe(text): return True

# رسائل، نصوص، delayed_send
try:
    from messages import delayed_send, get_welcome_message, WELCOME, HELP, SEARCHING, NO_MATCH, INTRO_PARTNER, LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER, REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED
except Exception:
    # تقديم بدائل بسيطة إذا لم يوجد ملف messages
    def delayed_send(bot_obj, chat_id, text, **kwargs):
        try:
            bot_obj.send_message(chat_id, text, **kwargs)
        except Exception:
            print("[delayed_send fallback] failed to send")
    def get_welcome_message(topic_key="START"):
        return "👋 أهلاً! مرحباً بك."
    WELCOME = "مرحباً!"
    HELP = "مساعدة: استخدم الأزرار."
    SEARCHING = "🔎 جارٍ البحث..."
    NO_MATCH = "لم نجد شريكًا الآن."
    INTRO_PARTNER = "لقد تمّ ربطك بشريك — ابدأ المحادثة!"
    LEAVE_CONFIRM = "هل أنت متأكد أنك تريد المغادرة؟"
    LEAVE_TOO_SOON = "لا يمكنك المغادرة الآن. انتظر {remain} ثانية."
    LEFT_YOU = "شريكك غادر المحادثة."
    LEFT_PARTNER = "لقد غادرت الدردشة."
    REPORT_CONFIRM = "هل تريد تأكيد الإبلاغ؟"
    REPORT_OK = "تم استلام الإبلاغ."
    REPORT_RESULT = "نتيجة الإبلاغ: {lines} أسطر."
    MUTED = "محظور مؤقتًا. تبقى {left} ثانية."
    BANNED = "لقد تم حظرك من النظام."

# Bad_word (إن وُجد)
try:
    from Bad_word import contains_bad_word, censor_text
except Exception:
    def contains_bad_word(text):
        return False
    def censor_text(text):
        return text

# ---------- إعدادات البوت ----------
TOKEN = os.environ.get("TELEGRAM_TOKEN") or getattr(__import__("config"), "TOKEN", None) if os.path.exists("config.py") else None
if not TOKEN:
    # حاول TELEGRAM_TOKEN كخيار بديل
    TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN أو BOT_TOKEN غير موجود في environment أو config.TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ---------- ثوابت الحالة (state constants) ----------
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

# ---------- لوحات المفاتيح المساعدة ----------
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
    from config import TOPICS
    for i in range(0, len(TOPICS), 2):
        row = [KeyboardButton(TOPICS[i])]
        if i + 1 < len(TOPICS):
            row.append(KeyboardButton(TOPICS[i+1]))
        kb.add(*row)
    return kb

def gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for g in getattr(__import__("config"), "GENDERS", ["ذكر", "أنثى"]):
        kb.add(KeyboardButton(g))
    return kb

def target_gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for tg in getattr(__import__("config"), "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"]):
        kb.add(KeyboardButton(tg))
    return kb

def yes_no_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# ---------- تحميل المستخدمين من التخزين ----------
try:
    load_users()
except Exception as e:
    print(f"[LOAD_USERS ERROR] {e}")

# ---------- دوال مساعدة لتحديث وحفظ المستخدم ----------
def update_user(uid: int, updates: dict):
    """
    تحديث قاموس المستخدم وحفظه. يستخدم ensure_user من profile (يضمن وجود السجل).
    """
    try:
        u = ensure_user(uid)
        u.update(updates)
        save_users()
    except Exception as e:
        # اطبع الخطأ كاملًا مع stacktrace لتشخيص أفضل
        print(f"[UPDATE_USER ERROR] {e} | uid={uid} | updates={updates}")
        print(traceback.format_exc())

def safe_send(uid: int, text: str, **kwargs):
    """
    غلاف للإرسال: لا نمرّر 'delay' هنا؛ messages.delayed_send يستقبل (bot, chat_id, text, **kwargs)
    """
    try:
        # استعمل delayed_send إن كان متاحًا (هو أفضل لمنع حظر الـ API عند إرسال متكرر)
        try:
            delayed_send(bot, uid, text, **kwargs)
        except Exception:
            # نرجع لbot.send_message المباشر كنسخة احتياطية
            bot.send_message(uid, text, **kwargs)
    except Exception as e:
        print(f"[SEND_MESSAGE ERROR] {e} | chat_id={uid} | text_preview={str(text)[:120]}")
        print(traceback.format_exc())

# ---------- مساعدة لاستخراج مفتاح الموضوع بدون الايموجي ----------
def _topic_key(topic_text: str) -> str:
    if not topic_text:
        return ""
    parts = topic_text.split()
    return parts[-1] if parts else topic_text

# ---------------------------
# ---------- Handlers ----------
# ---------------------------

# /start
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    print(f"[START] user={uid}")

    # أرسل الترحيب الرئيسي (إن كان get_welcome_message متاح)
    try:
        safe_send(uid, get_welcome_message("START"))
    except Exception as e:
        print(f"[START SEND ERROR] {e}")

    # ضبط الحالة لانتظار الاسم ثم اسأل مباشرة
    try:
        update_user(uid, {"state": STATE_REGISTER_NAME})
    except Exception as e:
        print(f"[UPDATE USER (START) ERROR] {e}")

    try:
        safe_send(uid, "✏️ ما اسمك؟", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        print(f"[ASK NAME ERROR] {e}")

# /help
@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users.get(uid, {})
    if u.get("banned_full"):
        return
    safe_send(uid, HELP, reply_markup=main_menu(in_chat=bool(u.get("partner"))))

# ping للاختبار
@bot.message_handler(commands=["ping"])
def cmd_ping(m: Message):
    try:
        cid = m.chat.id
        print(f"[DEBUG] ping from {cid}")
        bot.send_message(cid, "pong")
    except Exception as e:
        print(f"[ERROR] ping handler: {e}")

# /profile
@bot.message_handler(commands=["profile"])
def cmd_profile(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]
    safe_send(uid, profile_text(u), reply_markup=main_menu(in_chat=bool(u.get("partner"))))

# /search (بحث عن دردشة) — مرادف لزر "🔍 البحث عن دردشة"
@bot.message_handler(commands=["search", "chat", "find"])
def cmd_search(m: Message):
    uid = m.from_user.id
    handle_search_request(uid)

# /leave
@bot.message_handler(commands=["leave", "exit"])
def cmd_leave(m: Message):
    uid = m.from_user.id
    handle_leave_request(uid)

# /report
@bot.message_handler(commands=["report"])
def cmd_report(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    update_user(uid, {"state": STATE_CONFIRM_REPORT})
    safe_send(uid, REPORT_CONFIRM, reply_markup=yes_no_menu())

# استقبال أي نص
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return

    state = u.get("state") or ""
    print(f"[MSG] from={uid} state={state} text={txt[:80]}")

    # ---------- حالات التسجيل (الاسم -> الجنس -> العمر) ----------
    if state == STATE_REGISTER_NAME:
        handle_register_name(uid, txt); return
    if state == STATE_REGISTER_GENDER:
        handle_register_gender(uid, txt); return
    if state == STATE_REGISTER_AGE:
        handle_register_age(uid, txt); return

    # ---------- حالات التعديل ----------
    if state == STATE_EDIT_NAME:
        handle_edit_name(uid, txt); return
    if state == STATE_EDIT_AGE:
        handle_edit_age(uid, txt); return

    # ---------- حالات التطبيق ----------
    if state == STATE_CHOOSE_TOPIC:
        handle_topic_selection(uid, txt); return
    if state == STATE_CHOOSE_TARGET_GENDER:
        handle_target_gender(uid, txt); return
    if state == STATE_CONFIRM_LEAVE:
        handle_leave_confirm(uid, u, txt); return
    if state == STATE_CONFIRM_REPORT:
        handle_report_text_confirm(uid, u, txt); return

    # ---------- أوامر من القائمة الرئيسية عبر الأزرار ----------
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

# ---------------------------
# دوال التسجيل خطوة بخطوة
# ---------------------------

def handle_register_name(uid: int, txt: str):
    # استخدم set_user_name من profile.py
    try:
        ok = set_user_name(uid, txt)
        if not ok:
            safe_send(uid, "❌ الاسم غير صالح. استخدم 2–30 حرفًا (حروف ومسافات فقط). حاول مرة أخرى:")
            return
        update_user(uid, {"state": STATE_REGISTER_GENDER})
        safe_send(uid, f"✅ تم حفظ الاسم: {users[uid].get('name')}")
        # اطلب الجنس مع لوحة أزرار
        safe_send(uid, "💡 اختر جنسك (مرة واحدة):", reply_markup=gender_menu())
    except Exception as e:
        print(f"[handle_register_name ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء حفظ الاسم. حاول مرة أخرى.")

def handle_register_gender(uid: int, txt: str):
    try:
        txt = txt.strip()
        valid = getattr(__import__("config"), "GENDERS", ["ذكر", "أنثى"])
        if txt not in valid:
            safe_send(uid, "❌ اختر: ذكر / أنثى", reply_markup=gender_menu())
            return
        ok = set_user_gender(uid, txt)
        if not ok:
            safe_send(uid, "❌ اختيار غير صالح. اختر: ذكر / أنثى", reply_markup=gender_menu())
            return
        update_user(uid, {"state": STATE_REGISTER_AGE})
        safe_send(uid, f"✅ تم حفظ الجنس: {txt}")
        safe_send(uid, "🎂 ما عمرك؟ (10–120)", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        print(f"[handle_register_gender ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء حفظ الجنس. حاول مرة أخرى.")

def handle_register_age(uid: int, txt: str):
    try:
        ok = set_user_age(uid, txt)
        if not ok:
            safe_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120:")
            return
        update_user(uid, {"state": None})
        safe_send(uid, f"✅ تم حفظ العمر: {users[uid].get('age')}")
        safe_send(uid, "🎉 تم إعداد ملفك الشخصي بنجاح! يمكنك الآن استخدام القائمة:", reply_markup=main_menu(in_chat=False))
    except Exception as e:
        print(f"[handle_register_age ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء حفظ العمر. حاول مرة أخرى.")

# ---------------------------
# دوال التعديل (الاسم/العمر)
# ---------------------------

def handle_edit_name(uid: int, txt: str):
    try:
        ok = set_user_name(uid, txt)
        if not ok:
            safe_send(uid, "❌ الاسم غير صالح. حاول مجددًا:")
            return
        update_user(uid, {"state": None})
        safe_send(uid, f"✅ تم تحديث الاسم إلى: {users[uid].get('name')}", reply_markup=main_menu(in_chat=False))
    except Exception as e:
        print(f"[handle_edit_name ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء تعديل الاسم.")

def handle_edit_age(uid: int, txt: str):
    try:
        ok = set_user_age(uid, txt)
        if not ok:
            safe_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120:")
            return
        update_user(uid, {"state": None})
        safe_send(uid, f"✅ تم تحديث العمر إلى: {users[uid].get('age')}", reply_markup=main_menu(in_chat=False))
    except Exception as e:
        print(f"[handle_edit_age ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء تعديل العمر.")

# ---------------------------
# البحث عن دردشة و المطابقة
# ---------------------------

def handle_search_request(uid: int):
    ensure_user(uid)
    u = users[uid]
    if u.get("partner"):
        safe_send(uid, "⚠️ أنت بالفعل في دردشة!", reply_markup=main_menu(in_chat=True))
        return
    update_user(uid, {"state": STATE_CHOOSE_TOPIC})
    safe_send(uid, "اختر موضوع النقاش:", reply_markup=topics_menu())

def handle_topic_selection(uid: int, txt: str):
    txt = txt.strip()
    from config import TOPICS
    if txt not in TOPICS:
        safe_send(uid, "❌ اختر موضوعًا صالحًا من القائمة.", reply_markup=topics_menu())
        return
    update_user(uid, {"topic": txt, "state": STATE_CHOOSE_TARGET_GENDER})
    safe_send(uid, f"تم اختيار الموضوع: {txt}\nالآن اختر جنس الطرف الذي تريده:", reply_markup=target_gender_menu())

def handle_target_gender(uid: int, txt: str):
    txt = txt.strip()
    valid = getattr(__import__("config"), "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"])
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

    # رسالة ترحيب خاصة للموضوع + رسالة "جاري البحث"
    safe_send(uid, get_welcome_message(_topic_key(topic)))
    safe_send(uid, SEARCHING, reply_markup=main_menu(in_chat=False))

    # أضف إلى الانتظار وجرب المطابقة
    try:
        add_to_wait(topic, uid, target)
    except Exception:
        try:
            add_to_wait(uid, topic, target)
        except Exception as e:
            print(f"[add_to_wait ERROR] {e}")
    # حاول المطابقة (واجهات try_match قد تختلف)
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
                start_history(users[uid])
                start_history(users[pid])
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

# ---------------------------
# مغادرة الدردشة
# ---------------------------

def handle_leave_request(uid: int):
    ensure_user(uid)
    u = users[uid]
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    if elapsed < getattr(__import__("config"), "LEAVE_DELAY", 30):
        safe_send(uid, LEAVE_TOO_SOON.format(remain=int(getattr(__import__("config"), "LEAVE_DELAY", 30) - elapsed)))
        return
    update_user(uid, {"state": STATE_CONFIRM_LEAVE})
    safe_send(uid, LEAVE_CONFIRM, reply_markup=yes_no_menu())

def handle_leave_confirm(uid: int, u: dict, txt: str):
    if txt == "نعم ✅":
        pid = u.get("partner")
        if pid:
            try:
                # end_session يتوقع user objects أو ids حسب implemention
                try:
                    end_session(users[uid], users[pid])
                except Exception:
                    end_session(users.get(uid), users.get(pid))
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

# ---------------------------
# تأكيد الإبلاغ (نص)
# ---------------------------

def handle_report_text_confirm(uid: int, u: dict, txt: str):
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
            try:
                safe_send(uid, REPORT_RESULT.format(lines=result[0], respect=u.get("respect", "—")))
            except Exception:
                pass
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

# ---------------------------
# تمرير الرسائل بين الشركاء
# ---------------------------

def handle_chat_message(uid: int, txt: str, u: dict):
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

# ---------------------------
# Webhook endpoint (Flask)
# ---------------------------

@app.route(f"/{getattr(__import__("config"), 'WEBHOOK_PATH', 'webhook')}", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"[WEBHOOK PROCESS ERROR] {e}\n{traceback.format_exc()}")
    return "", 200

def set_webhook():
    url = os.environ.get("WEBHOOK_URL") or getattr(__import__("config"), "WEBHOOK_URL", None) if os.path.exists("config.py") else None
    path = getattr(__import__("config"), "WEBHOOK_PATH", "webhook") if os.path.exists("config.py") else "webhook"
    if not url:
        raise RuntimeError("WEBHOOK_URL مفقود. ضعه في Environment أو config.WEBHOOK_URL")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.set_webhook(f"{url}/{path}")
    print(f"[WEBHOOK] Set to {url}/{path}")

# ---------- تشغيل watcher إن وُجد ----------
try:
    start_timeout_watcher(bot)
except Exception:
    try:
        start_timeout_watcher()
    except Exception as e:
        print(f"[start_timeout_watcher ERROR] {e}")

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
    port = int(os.environ.get("PORT", getattr(__import__("config"), "PORT", 5000)) if os.path.exists("config.py") else int(os.environ.get("PORT", 5000)))
    print(f"[RUN] Webhook listening on port {port}…")
    app.run(host="0.0.0.0", port=port)
