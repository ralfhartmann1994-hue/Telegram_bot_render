import os
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import ReplyKeyboardRemove
import threading

# ===== الإعدادات =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("ضع TELEGRAM_TOKEN في إعدادات البيئة")

bot = telebot.TeleBot(TOKEN)

# ===== البيانات =====
users = {}  # user_id -> {"name", "age", "gender", "respect", "gender_changed", "step"}
waiting_users = {}  # (topic, gender) -> [user_ids]
active_chats = {}  # user_id -> partner_id
leave_timers = {}  # user_id -> بدء المحادثة
chat_logs = {}  # user_id -> [("me"/"partner", msg)]
banned_users = {}  # user_id -> ban_end_timestamp
warnings_sent = set()

TOPICS = ["فلسفة", "رياضة", "دين", "سياسة", "تعارف"]
GENDERS = ["ذكر", "أنثى"]

bad_words = [
    "كس","كسمك","كسي","كسس","كسسس","كسسسس","كسمو","كصمك","اير","ايري","ايرنا","طيزنا","طيز",
    "كسختك","يلعن ربك","يلعن دينك","يلعن روحك","عنربك","عندينك","يلعن شفراتك","قحبة","شرموطة",
    "شلكة","منتاكة","سرموطة","قحب","شرموط","منيك","مكسكس"
]

# ===== دوال مساعدة =====
def get_respect_badge(score):
    if score >= 80: return "🌟"
    if score >= 60: return "🙂"
    if score >= 50: return "⚠️"
    if score >= 40: return "⚠️"
    return "🚫"

def get_penalty(respect, bad_count):
    penalty = 0
    if respect >= 76: penalty = bad_count // 2
    elif 71 <= respect <= 75: penalty = bad_count
    elif 61 <= respect <= 70: penalty = bad_count * 2
    elif 51 <= respect <= 60: penalty = bad_count * 3
    elif 41 <= respect <= 50: penalty = bad_count * 5
    elif 26 <= respect <= 40: penalty = bad_count * 10
    return penalty

def is_banned(user_id):
    if user_id in banned_users:
        if time.time() < banned_users[user_id]:
            return True
        else:
            del banned_users[user_id]
    return False

def add_to_log(user_id, sender, text):
    if user_id not in chat_logs:
        chat_logs[user_id] = []
    chat_logs[user_id].append((sender, text))
    if len(chat_logs[user_id]) > 50:
        chat_logs[user_id] = chat_logs[user_id][-50:]

# ===== أزرار دائمة =====
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🏠 الرئيسية"), KeyboardButton("👤 الملف الشخصي"), KeyboardButton("🔍 البحث"))
    return kb

# ===== البداية =====
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    if is_banned(uid):
        bot.send_message(uid, "⛔ أنت محظور حالياً.")
        return
    if uid not in users:
        users[uid] = {"name": None, "age": None, "gender": None, "respect": 80, "gender_changed":0, "step":"name"}
        bot.send_message(uid, "👋 أهلاً! لنبدأ بإنشاء ملفك الشخصي.\nما اسمك؟", reply_markup=main_menu())
    else:
        users[uid]["step"] = None
        bot.send_message(uid, "مرحباً بعودتك!", reply_markup=main_menu())

# ===== جمع البيانات =====
@bot.message_handler(func=lambda m: users.get(m.from_user.id, {}).get("step")=="name")
def set_name(msg):
    uid = msg.from_user.id
    users[uid]["name"] = msg.text[:64]
    users[uid]["step"] = "age"
    bot.send_message(uid, "🎂 ما هو عمرك؟")

@bot.message_handler(func=lambda m: users.get(m.from_user.id, {}).get("step")=="age")
def set_age(msg):
    uid = msg.from_user.id
    if not msg.text.isdigit():
        bot.send_message(uid, "⚠️ أدخل العمر كرقم.")
        return
    users[uid]["age"] = int(msg.text)
    users[uid]["step"] = "gender"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👨 ذكر", "👩 أنثى")
    bot.send_message(uid, "🚻 اختر جنسك:", reply_markup=kb)

@bot.message_handler(func=lambda m: users.get(m.from_user.id, {}).get("step")=="gender")
def set_gender(msg):
    uid = msg.from_user.id
    if msg.text not in ["👨 ذكر","👩 أنثى"]:
        bot.send_message(uid, "❌ اختر من الأزرار فقط.")
        return
    users[uid]["gender"] = "ذكر" if "ذكر" in msg.text else "أنثى"
    users[uid]["step"] = None
    bot.send_message(uid, "✅ تم حفظ ملفك الشخصي!", reply_markup=main_menu())

# ===== الملف الشخصي =====
@bot.message_handler(func=lambda m: m.text=="👤 الملف الشخصي")
def profile_menu(msg):
    uid = msg.from_user.id
    u = users.get(uid)
    if not u:
        bot.send_message(uid, "ℹ️ اكتب /start أولاً.")
        return
    badge = get_respect_badge(u["respect"])
    info = f"👤 الاسم: {u['name']}\n🎂 العمر: {u['age']}\n⚧️ الجنس: {u['gender']}\n⭐ الاحترام: {u['respect']} {badge}"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✏️ تعديل الاسم", "✏️ تعديل العمر", "🚻 تعديل الجنس")
    kb.add("⬅️ رجوع")
    bot.send_message(uid, info, reply_markup=kb)

# ===== البحث والمطابقة =====
@bot.message_handler(func=lambda m: m.text=="🔍 البحث")
def search_menu(msg):
    uid = msg.from_user.id
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in TOPICS:
        kb.add(f"{t} 👨", f"{t} 👩")
    kb.add("⬅️ رجوع")
    bot.send_message(uid, "ماذا تريد أن تناقش اليوم؟ اختر المجال والجنس:", reply_markup=kb)

def find_partner(user_id, topic, target_gender):
    key = (topic, target_gender)
    opposite_gender = "أنثى" if users[user_id]["gender"]=="ذكر" else "ذكر"
    partner_key = (topic, opposite_gender)
    if partner_key in waiting_users and waiting_users[partner_key]:
        partner_id = waiting_users[partner_key].pop(0)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        leave_timers[user_id] = time.time()
        leave_timers[partner_id] = time.time()
        # البيانات
        bot.send_message(user_id, f"🎉 تم إيجاد شريك!\n👤 {users[partner_id]['name']}\n🎂 {users[partner_id]['age']}\n⭐ {users[partner_id]['respect']}")
        bot.send_message(partner_id, f"🎉 تم إيجاد شريك!\n👤 {users[user_id]['name']}\n🎂 {users[user_id]['age']}\n⭐ {users[user_id]['respect']}")
        bot.send_message(user_id, "يمكنك بدء المحادثة الآن ✅")
        bot.send_message(partner_id, "يمكنك بدء المحادثة الآن ✅")
    else:
        if key not in waiting_users:
            waiting_users[key] = []
        waiting_users[key].append(user_id)
        bot.send_message(user_id, "⏳ لم يتم العثور على شريك، سيتم مطابقتك لاحقاً.")

@bot.message_handler(func=lambda m: any(t in m.text for t in TOPICS))
def handle_topic_choice(msg):
    user_id = msg.from_user.id
    for t in TOPICS:
        if t in msg.text:
            target_gender = "ذكر" if "👨" in msg.text else "أنثى"
            find_partner(user_id, t, target_gender)
            break

# ===== إعادة توجيه الرسائل =====
@bot.message_handler(func=lambda msg: True)
def relay(msg):
    user_id = msg.from_user.id
    text = msg.text
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ أنت محظور من استخدام البوت حالياً.")
        return
    add_to_log(user_id, "me", text)
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        add_to_log(partner_id, "partner", text)
        bot.send_message(partner_id, f"💬 {users[user_id]['name']}: {text}")
    else:
        bot.send_message(user_id, "ℹ️ لا يوجد شريك نشط، اضغط 🔍 البحث.")

# ===== زر المغادرة =====
@bot.message_handler(func=lambda msg: msg.text=="❌ مغادرة 🚪")
def leave_chat(msg):
    user_id = msg.from_user.id
    if user_id not in active_chats:
        bot.send_message(user_id, "ℹ️ لست في محادثة حالياً.")
        return
    elapsed = time.time() - leave_timers.get(user_id, 0)
    if elapsed < 30:
        bot.send_message(user_id, f"⏳ لا يمكنك المغادرة قبل 30 ثانية. تبقى {int(30-elapsed)} ثانية.")
        return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("تأكيد المغادرة 🚪", callback_data=f"confirm_leave_{user_id}"))
    bot.send_message(user_id, "هل تريد فعلاً المغادرة؟", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_leave_"))
def confirm_leave(call):
    user_id = int(call.data.split("_")[-1])
    if user_id not in active_chats:
        bot.answer_callback_query(call.id, "ℹ️ لا يوجد شريك.")
        return
    partner_id = active_chats[user_id]
    bot.send_message(user_id, "🚪 غادرت الدردشة.")
    bot.send_message(partner_id, "🚪 شريكك غادر الدردشة.")
    for uid in [user_id, partner
