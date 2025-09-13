# Main.py (مصحح لحل مشكلة التسجيل)
import os
import time
import traceback
import importlib
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message

# استيراد إعدادات ورسائل وستيكرات
config = importlib.import_module("config")
from messages import (
    delayed_send, get_welcome_message, WELCOME, HELP, SEARCHING, NO_MATCH, 
    INTRO_PARTNER, LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER, 
    REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED, PROFILE_SAVED
)
from stickers import STICKERS

# ملفات المشروع
import storage
from storage import load_users, save_users, ensure_user, update_user_dict, append_history
import Profile_manger as ProfileManager

# Matchmaking + Moderation (مع معالجة fallbacks)
try:
    from Matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
except Exception as e:
    print(f"[IMPORT Matchmaking ERROR] {e}")
    def add_to_wait(*args, **kwargs): 
        raise RuntimeError("Matchmaking.add_to_wait unavailable")
    def try_match(*args, **kwargs): return None
    def start_timeout_watcher(bot=None): return
    def remove_from_wait(*args, **kwargs): return

try:
    from Moderation import is_muted, apply_respect, review_history_and_penalize, check_message_safe, contains_bad_word, censor_text
except Exception as e:
    print(f"[IMPORT Moderation ERROR] {e}")
    # fallbacks
    def is_muted(uid): return False
    def apply_respect(uid, text): return 0
    def review_history_and_penalize(uid, pid, history): return (0,0,0,0)
    def check_message_safe(text): return True
    def contains_bad_word(text): return []
    def censor_text(text): return text

# إعداد البوت
TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN") or (getattr(config, "TOKEN", None) if hasattr(config, "TOKEN") else None)
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN / BOT_TOKEN غير معرف في environment أو config.TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ثوابت حالات
STATE_REGISTER_NAME = "REGISTER_NAME"
STATE_REGISTER_GENDER = "REGISTER_GENDER"
STATE_REGISTER_AGE = "REGISTER_AGE"
STATE_EDIT_NAME = "EDIT_NAME"
STATE_EDIT_AGE = "EDIT_AGE"
STATE_CHOOSE_TOPIC = "CHOOSE_TOPIC"
STATE_CHOOSE_TARGET_GENDER = "CHOOSE_TARGET_GENDER"
STATE_SEARCHING = "SEARCHING"
STATE_CONFIRM_LEAVE = "CONFIRM_LEAVE"
STATE_CONFIRM_REPORT = "CONFIRM_REPORT"

# كيبوردات مساعدة
def main_menu(in_chat: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("👤 ملفي"))
    kb.add(KeyboardButton("✏️ تعديل الاسم"), KeyboardButton("🎂 تعديل العمر"))
    kb.add(KeyboardButton("🔍 البحث عن دردشة"))
    if in_chat:
        kb.add(KeyboardButton("🚨 إبلاغ"), KeyboardButton("🚪 مغادرة الدردشة"))
    kb.add(KeyboardButton("تواصل مع الدعم"))
    return kb

def topics_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    try:
        TOPICS = getattr(config, "TOPICS", ["عام"])
        for i in range(0, len(TOPICS), 2):
            row = [KeyboardButton(TOPICS[i])]
            if i+1 < len(TOPICS):
                row.append(KeyboardButton(TOPICS[i+1]))
            kb.add(*row)
    except Exception:
        kb.add(KeyboardButton("عام"))
    return kb

def gender_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for g in getattr(config, "GENDERS", ["ذكر", "أنثى"]):
        kb.add(KeyboardButton(g))
    return kb

def target_gender_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for tg in getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"]):
        kb.add(KeyboardButton(tg))
    return kb

def yes_no_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# تحميل المستخدمين عند بدء التشغيل
try:
    load_users()
except Exception as e:
    print(f"[LOAD_USERS ERROR] {e}")

# امتدادات لضمان الحقول الأساسية
def ensure_user_extended(uid: int):
    u = ensure_user(uid)
    # تغيير نقاط الاحترام إلى 80 بدلاً من 100
    if "points" not in u:
        u["points"] = u.get("points", 80)
    if "respect" not in u:
        u["respect"] = u.get("respect", 80)
    if "referrer" not in u:
        u["referrer"] = u.get("referrer", None)
    if "referral_code" not in u:
        u["referral_code"] = u.get("referral_code", None)
    if "state" not in u:
        u["state"] = None
    u.setdefault("partner", None)
    u.setdefault("history", [])
    save_users()
    return u

# دوال مساعدة
def update_user(uid: int, updates: dict):
    try:
        # استخدم storage.users مباشرة
        if uid not in storage.users:
            ensure_user_extended(uid)
        for key, value in updates.items():
            storage.users[uid][key] = value
        storage.save_users()
        print(f"[UPDATE_USER] Success for uid={uid}, updates={updates}")
    except Exception as e:
        print(f"[UPDATE_USER ERROR] {e} | uid={uid} | updates={updates}")
        print(traceback.format_exc())

def safe_send(uid: int, text: str, **kwargs):
    try:
        delayed_send(bot, uid, text, **kwargs)
    except Exception:
        try:
            bot.send_message(uid, text, **kwargs)
        except Exception as e:
            print(f"[SEND ERROR] {e} | uid={uid} | preview={str(text)[:120]}")

def safe_send_sticker(uid: int, sticker_id: str):
    try:
        bot.send_sticker(uid, sticker_id)
    except Exception as e:
        print(f"[STICKER ERROR] {e} | uid={uid} | sticker={sticker_id}")

def partner_profile_text(pid: int):
    try:
        p = storage.users.get(pid)
        if not p:
            return "معلومات الشريك غير متوفرة."
        name = p.get("name") or "غير محدد"
        age = p.get("age") or "غير محدد"
        gender = p.get("gender") or "غير محدد"
        respect = p.get("respect", 80)
        return f"👤 <b>تم إيجاد شريك لك</b>\n• الاسم: {name}\n• العمر: {age}\n• الجنس: {gender}\n• الاحترام: ⭐ {respect}"
    except Exception as e:
        print(f"[partner_profile_text ERROR] {e}")
        return "معلومات الشريك غير متوفرة."

# معالجات الأوامر
@bot.message_handler(commands=['start'])
def cmd_start(message: Message):
    uid = message.from_user.id
    u = ensure_user_extended(uid)
    
    print(f"[START COMMAND] uid={uid}, current user data: {u}")

    # إذا كان المستخدم جديدًا أو لم يُسجل اسمه
    if not u.get("name"):
        print(f"[START] New user registration for uid={uid}")
        
        # إرسال رسالة ترحيبية عشوائية أولاً
        welcome_msg = get_welcome_message("START")
        safe_send(uid, welcome_msg)
        
        # ثم إرسال الستيكر الترحيبي
        try:
            safe_send_sticker(uid, STICKERS.get("welcome_general"))
        except Exception as e:
            print(f"[START] Sticker error: {e}")

        # بدء خطوة التسجيل بالاسم
        print(f"[START] About to set state to REGISTER_NAME")
        
        try:
            storage.users[uid]["state"] = STATE_REGISTER_NAME
            storage.save_users()
            print(f"[START] State set directly in storage")
            
            # تأكد من الحفظ
            saved_user = storage.users.get(uid, {})
            print(f"[START] Verification - saved user state: {saved_user.get('state')}")
            
        except Exception as e:
            print(f"[START] Error setting state: {e}")
            print(traceback.format_exc())
        
        # إرسال رسالة طلب الاسم
        safe_send(uid, "💡 لنبدأ بإنشاء ملفك الشخصي.\n\n👤 ما هو اسمك؟ (2-30 حرف)", 
                 reply_markup=ReplyKeyboardRemove())
        
        print(f"[START] Registration process started for uid={uid}")
        
    else:
        # المستخدم قديم، نرحب به مع قائمة رئيسية
        print(f"[START] Existing user: {u.get('name')}")
        safe_send(uid, f"👋 مرحبًا مجددًا، {u.get('name')}!\n\nماذا تريد أن تفعل اليوم؟", 
                 reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["profile"])
def cmd_profile(m: Message):
    uid = m.from_user.id
    ensure_user_extended(uid)
    u = storage.users[uid]
    safe_send(uid, ProfileManager.profile_text(u), 
             reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["help", "support"])
def cmd_support(m: Message):
    uid = m.from_user.id
    ensure_user_extended(uid)
    support_handle = "@MAA2857"
    safe_send(uid, f"للتواصل مع الدعم تواصل عبر: {support_handle}\nأو أرسل رسالة هنا وسنحاول الرد إن أمكن.")

@bot.message_handler(commands=["search", "chat", "find"])
def cmd_search(m: Message):
    uid = m.from_user.id
    handle_search_request(uid)

@bot.message_handler(commands=["leave", "exit"])
def cmd_leave(m: Message):
    uid = m.from_user.id
    handle_leave_request(uid)

@bot.message_handler(commands=["report"])
def cmd_report(m: Message):
    uid = m.from_user.id
    ensure_user_extended(uid)
    storage.users[uid]["state"] = STATE_CONFIRM_REPORT
    storage.save_users()
    safe_send(uid, REPORT_CONFIRM, reply_markup=yes_no_menu())

# معالج الرسائل النصية المُصحح
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    try:
        uid = m.from_user.id
        txt = (m.text or "").strip()
        
        print(f"[MESSAGE RECEIVED] uid={uid}, text='{txt}'")
        
        ensure_user_extended(uid)
        u = storage.users.get(uid, {})
        print(f"[USER DATA] uid={uid}, user={u}")
        
        if u.get("banned_full"):
            safe_send(uid, BANNED)
            return
            
        state = u.get("state") or ""
        print(f"[STATE CHECK] uid={uid}, state='{state}'")

        # معالجة حالات التسجيل أولاً
        if state == STATE_REGISTER_NAME:
            print(f"[REGISTER_NAME MATCH] Processing for uid={uid}")
            handle_register_name(uid, txt)
            return
        elif state == STATE_REGISTER_GENDER:
            print(f"[REGISTER_GENDER MATCH] Processing for uid={uid}")
            handle_register_gender(uid, txt)
            return
        elif state == STATE_REGISTER_AGE:
            print(f"[REGISTER_AGE MATCH] Processing for uid={uid}")
            handle_register_age(uid, txt)
            return

        # معالجة حالات التعديل
        elif state == STATE_EDIT_NAME:
            handle_edit_name(uid, txt)
            return
        elif state == STATE_EDIT_AGE:
            handle_edit_age(uid, txt)
            return

        # معالجة حالات البحث
        elif state == STATE_CHOOSE_TOPIC:
            handle_topic_selection(uid, txt)
            return
        elif state == STATE_CHOOSE_TARGET_GENDER:
            handle_target_gender(uid, txt)
            return

        # معالجة حالات التأكيد
        elif state == STATE_CONFIRM_LEAVE:
            handle_leave_confirm(uid, u, txt)
            return
        elif state == STATE_CONFIRM_REPORT:
            handle_report_text_confirm(uid, u, txt)
            return

        print(f"[BUTTON CHECK] Checking buttons for: '{txt}'")

        # زر "تواصل مع الدعم"
        if txt == "تواصل مع الدعم":
            support_handle = "@MAA2857"
            safe_send(uid, f"للتواصل مع الدعم: {support_handle}\nأخبرنا بالمشكلة وسنراجعها.")
            return

        # اعتراض أزرار المغادرة/إبلاغ
        if txt == "🚪 مغادرة الدردشة":
            handle_leave_request(uid)
            return
        if txt == "🚨 إبلاغ":
            storage.users[uid]["state"] = STATE_CONFIRM_REPORT
            storage.save_users()
            safe_send(uid, REPORT_CONFIRM, reply_markup=yes_no_menu())
            return

        # قائمة رئيسية
        if txt == "👤 ملفي":
            safe_send(uid, ProfileManager.profile_text(u), 
                     reply_markup=main_menu(in_chat=bool(u.get("partner"))))
            return
        elif txt == "✏️ تعديل الاسم":
            storage.users[uid]["state"] = STATE_EDIT_NAME
            storage.save_users()
            safe_send(uid, "✏️ أرسل الاسم الجديد:", reply_markup=ReplyKeyboardRemove())
            return
        elif txt == "🎂 تعديل العمر":
            storage.users[uid]["state"] = STATE_EDIT_AGE
            storage.save_users()
            safe_send(uid, "🎂 أرسل العمر الجديد (10–120):", reply_markup=ReplyKeyboardRemove())
            return
        elif txt == "🆘 مساعدة":
            support_handle = "@MAA2857"
            safe_send(uid, f"تواصل مع الدعم: {support_handle}")
            return
        elif txt == "🔍 البحث عن دردشة":
            handle_search_request(uid)
            return

        # إذا المستخدم داخل دردشة، مرّر للمعالجة الخاصة بالدردشة
        if u.get("partner"):
            handle_chat_message(uid, txt, u)
            return

        print(f"[DEFAULT] No match found for uid={uid}, text='{txt}'")
        # افتراضي
        safe_send(uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", 
                 reply_markup=main_menu(in_chat=False))

    except Exception as e:
        print(f"[ON_TEXT ERROR] {e}")
        print(traceback.format_exc())

# دوال التسجيل المُصححة
def handle_register_name(uid: int, txt: str):
    print(f"[REGISTER_NAME START] uid={uid}, text='{txt}'")
    
    if len(txt) < 2 or len(txt) > 30:
        safe_send(uid, "❌ الاسم غير صالح، استخدم 2–30 حرفًا. حاول مرة أخرى:")
        return

    try:
        # حفظ الاسم مباشرة في storage
        storage.users[uid]["name"] = txt
        storage.users[uid]["state"] = STATE_REGISTER_GENDER
        storage.save_users()
        
        print(f"[REGISTER_NAME] Name and state saved successfully")
        
        # إرسال ستيكر بعد الاسم
        try:
            safe_send_sticker(uid, STICKERS.get("after_name"))
        except Exception as e:
            print(f"[REGISTER_NAME] Sticker send error: {e}")
        
        # طلب اختيار الجنس
        safe_send(uid, f"✅ أهلاً {txt}! 👋\n\n💡 الآن اختر جنسك:", reply_markup=gender_menu())
        
    except Exception as e:
        print(f"[handle_register_name ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء حفظ الاسم. حاول مرة أخرى:")

def handle_register_gender(uid: int, txt: str):
    print(f"[REGISTER_GENDER START] uid={uid}, text='{txt}'")
    
    valid_genders = getattr(config, "GENDERS", ["ذكر", "أنثى"])
    if txt not in valid_genders:
        safe_send(uid, f"❌ اختر جنسًا صالحًا من: {' / '.join(valid_genders)}", 
                 reply_markup=gender_menu())
        return

    try:
        storage.users[uid]["gender"] = txt
        storage.users[uid]["state"] = STATE_REGISTER_AGE
        storage.save_users()
        
        print(f"[REGISTER_GENDER] Gender and state saved successfully")
        
        safe_send(uid, f"✅ تم حفظ الجنس: {txt}\n🎂 ما عمرك؟ (10–120)", 
                 reply_markup=ReplyKeyboardRemove())
        
    except Exception as e:
        print(f"[handle_register_gender ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء حفظ الجنس. حاول مرة أخرى:")

def handle_register_age(uid: int, txt: str):
    print(f"[REGISTER_AGE START] uid={uid}, text='{txt}'")
    
    try:
        age = int(txt)
    except ValueError:
        safe_send(uid, "❌ من فضلك أدخل العمر كرقم بين 10 و120:")
        return

    if age < 10 or age > 120:
        safe_send(uid, "❌ العمر غير منطقي. حاول مرة أخرى (10–120):")
        return

    try:
        storage.users[uid]["age"] = age
        storage.users[uid]["state"] = None
        storage.save_users()
        
        print(f"[REGISTER_AGE] Age saved and state cleared successfully")
        
        u = storage.users.get(uid, {})
        profile_msg = PROFILE_SAVED.format(
            name=u.get("name", "غير محدد"),
            gender=u.get("gender", "غير محدد"),
            age=u.get("age", "غير محدد")
        )
        
        safe_send(uid, profile_msg, reply_markup=main_menu(in_chat=False))
        
        try:
            safe_send_sticker(uid, STICKERS.get("registration_complete", STICKERS.get("welcome_general")))
        except Exception as e:
            print(f"[REGISTER_AGE] Sticker error: {e}")
            
    except Exception as e:
        print(f"[handle_register_age ERROR] {e}")
        print(traceback.format_exc())
        safe_send(uid, "❌ حدث خطأ أثناء حفظ العمر. حاول مرة أخرى:")

def handle_edit_name(uid: int, txt: str):
    try:
        if len(txt) < 2 or len(txt) > 30:
            safe_send(uid, "❌ الاسم غير صالح (2-30 حرف). حاول مجددًا:")
            return
            
        storage.users[uid]["name"] = txt
        storage.users[uid]["state"] = None
        storage.save_users()
        
        safe_send(uid, f"✅ تم تحديث الاسم إلى: {txt}", 
                 reply_markup=main_menu(in_chat=False))
    except Exception as e:
        print(f"[handle_edit_name ERROR] {e}")
        safe_send(uid, "❌ حدث خطأ أثناء تعديل الاسم.")

def handle_edit_age(uid: int, txt: str):
    try:
        age = int(txt)
        if age < 10 or age > 120:
            safe_send(uid, "❌ العمر غير صالح. أرسل رقمًا بين 10 و120:")
            return
            
        storage.users[uid]["age"] = age
        storage.users[uid]["state"] = None
        storage.save_users()
        
        safe_send(uid, f"✅ تم تحديث العمر إلى: {age}", 
                 reply_markup=main_menu(in_chat=False))
    except Exception as e:
        print(f"[handle_edit_age ERROR] {e}")
        safe_send(uid, "❌ حدث خطأ أثناء تعديل العمر.")

def handle_search_request(uid: int):
    ensure_user_extended(uid)
    u = storage.users.get(uid, {})
    
    if u.get("partner"):
        safe_send(uid, "⚠️ أنت بالفعل في دردشة!", 
                 reply_markup=main_menu(in_chat=True))
        return
        
    storage.users[uid]["state"] = STATE_CHOOSE_TOPIC
    storage.save_users()
    
    safe_send(uid, "اختر موضوع النقاش:", reply_markup=topics_menu())

def handle_topic_selection(uid: int, txt: str):
    try:
        TOPICS = getattr(config, "TOPICS", ["عام"])
    except Exception:
        TOPICS = ["عام"]
    
    if txt not in TOPICS:
        safe_send(uid, "❌ اختر موضوعًا صالحًا من القائمة.", reply_markup=topics_menu())
        return
        
    storage.users[uid]["topic"] = txt
    storage.users[uid]["state"] = STATE_CHOOSE_TARGET_GENDER
    storage.save_users()
    
    safe_send(uid, f"تم اختيار الموضوع: {txt}\nالآن اختر جنس الطرف الذي تريده:", 
             reply_markup=target_gender_menu())

def handle_target_gender(uid: int, txt: str):
    valid = getattr(config, "TARGET_GENDERS", ["👨 رجل", "👩 امرأة"])
    if txt not in valid:
        safe_send(uid, f"❌ اختر: {' / '.join(valid)}", reply_markup=target_gender_menu())
        return

    if "رجل" in txt:
        target = "male"
    elif "امرأة" in txt or "امرأ" in txt:
        target = "female"
    else:
        target = "any"

    u = storage.users.get(uid, {})
    topic = u.get("topic")
    
    storage.users[uid]["target_gender"] = target
    storage.users[uid]["state"] = STATE_SEARCHING
    storage.save_users()
    
    # أضف إلى الانتظار
    try:
        add_to_wait(topic, uid, target)
    except Exception as e:
        print(f"[add_to_wait ERROR] {e}")

    # رسالة البحث
    safe_send(uid, SEARCHING, reply_markup=ReplyKeyboardRemove())

    # حاول المطابقة فوراً
    partner = None
    try:
        partner = try_match(uid, topic)
    except Exception as e:
        print(f"[try_match ERROR] {e}")

    if partner:
        try:
            pid = int(partner)
            storage.users[uid]["partner"] = pid
            storage.users[uid]["state"] = None
            storage.users[uid]["chat_started_at"] = time.time()
            
            storage.users[pid]["partner"] = uid
            storage.users[pid]["state"] = None
            storage.users[pid]["chat_started_at"] = time.time()
            storage.save_users()
            
            ProfileManager.start_history(storage.users[uid])
            ProfileManager.start_history(storage.users[pid])
            
            safe_send(uid, partner_profile_text(pid), reply_markup=ReplyKeyboardRemove())
            safe_send(pid, partner_profile_text(uid), reply_markup=ReplyKeyboardRemove())
            safe_send(uid, INTRO_PARTNER, reply_markup=main_menu(in_chat=True))
            safe_send(pid, INTRO_PARTNER, reply_markup=main_menu(in_chat=True))
        except Exception as e:
            print(f"[MATCH SETUP ERROR] {e}")

    try:
        start_timeout_watcher(bot)
    except Exception as e:
        print(f"[start_timeout_watcher ERROR] {e}")

def handle_leave_request(uid: int):
    ensure_user_extended(uid)
    u = storage.users.get(uid, {})
    started = u.get("chat_started_at") or 0
    elapsed = time.time() - started
    leave_delay = getattr(config, "LEAVE_DELAY", 30)
    if elapsed < leave_delay:
        safe_send(uid, LEAVE_TOO_SOON.format(remain=int(leave_delay - elapsed)))
        return
    storage.users[uid]["state"] = STATE_CONFIRM_LEAVE
    storage.save_users()
    safe_send(uid, LEAVE_CONFIRM, reply_markup=yes_no_menu())

def handle_leave_confirm(uid: int, u: dict, txt: str):
    if txt == "نعم ✅":
        pid = u.get("partner")
        if pid:
            try:
                ProfileManager.end_session(storage.users[uid], storage.users[pid])
            except Exception:
                pass
                
            storage.users[uid]["partner"] = None
            storage.users[uid]["state"] = None
            storage.users[uid]["chat_started_at"] = None
            
            storage.users[pid]["partner"] = None
            storage.users[pid]["state"] = None
            storage.users[pid]["chat_started_at"] = None
            storage.save_users()
            
            safe_send(uid, "لقد غادرت الدردشة.", reply_markup=main_menu(in_chat=False))
            
            try:
                safe_send_sticker(pid, STICKERS.get("partner_left"))
                safe_send(pid, "شريكك غادر الدردشة.", reply_markup=main_menu(in_chat=False))
            except Exception:
                pass
        else:
            storage.users[uid]["state"] = None
            storage.save_users()
            safe_send(uid, "لم يتم العثور على شريك حالي.")
    elif txt == "لا ❌":
        storage.users[uid]["state"] = None
        storage.save_users()
        safe_send(uid, "تم الإلغاء. تابع الدردشة 👌")
    else:
        safe_send(uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())

def handle_report_text_confirm(uid: int, u: dict, txt: str):
    if txt == "نعم ✅":
        pid = u.get("partner")
        try:
            hist = []
            if pid and storage.users.get(pid):
                hist = storage.users[pid].get("history", [])
            res = review_history_and_penalize(uid, pid, hist)
            lines, badwords, penalty, new_respect = res
        except Exception as e:
            print(f"[review_history_and_penalize ERROR] {e}")
            res = (0,0,0, storage.users.get(pid, {}).get("respect", "—") if pid else "—")
            lines, badwords, penalty, new_respect = res
            
        storage.users[uid]["state"] = None
        storage.save_users()
        
        safe_send(uid, REPORT_OK)
        safe_send(uid, REPORT_RESULT.format(
            lines=lines, badwords=badwords, penalty=penalty, new_respect=new_respect
        ))
        
        # أخبر الشريك إن وُجد
        try:
            if pid:
                safe_send(pid, f"🔔 تم تلقي بلاغ ضدك. تم مراجعة المحادثة وخصم {penalty} نقطة احترام. الاحترام الآن: {new_respect}.")
        except Exception:
            pass
            
    elif txt == "لا ❌":
        storage.users[uid]["state"] = None
        storage.save_users()
        safe_send(uid, "تم الإلغاء. شكراً لحرصك.")
    else:
        safe_send(uid, "اختر: نعم ✅ / لا ❌", reply_markup=yes_no_menu())
        return
        
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🚪 مغادرة الدردشة"))
    safe_send(uid, "هل تريد الآن مغادرة الدردشة؟", reply_markup=kb)

def handle_chat_message(uid: int, txt: str, u: dict):
    if txt in ("🚪 مغادرة الدردشة", "🚨 إبلاغ", "تواصل مع الدعم"):
        return

    # تحقق الحظر الجزئي
    if u.get("muted_until") and time.time() < int(u.get("muted_until")):
        left = int(int(u.get("muted_until")) - time.time())
        safe_send(uid, MUTED.format(left=left))
        return

    try:
        bad = contains_bad_word(txt)
        if bad:
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
    if not pid or pid not in storage.users:
        storage.users[uid]["partner"] = None
        storage.save_users()
        safe_send(uid, "لا يوجد شريك حالي — عد إلى القائمة.", reply_markup=main_menu(in_chat=False))
        return

    try:
        bot.send_message(pid, f"💬 {txt_to_send}")
    except Exception as e:
        print(f"[SEND TO PARTNER ERROR] {e}")
        safe_send(uid, "حدث خطأ أثناء إرسال الرسالة إلى الشريك.")

# Webhook endpoint
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
    url = getattr(config, "WEBHOOK_URL", None)
    path = getattr(config, "WEBHOOK_PATH", "webhook")
    if not url:
        print("[WEBHOOK] WEBHOOK_URL not set; skipping webhook setup")
        return
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.set_webhook(f"{url}/{path}")
    print(f"[WEBHOOK] Set to {url}/{path}")

# شغل watcher للمطابقة
try:
    start_timeout_watcher(bot)
except Exception as e:
    print(f"[start_timeout_watcher ERROR] {e}")

# نقطة التشغيل
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
