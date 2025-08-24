import os
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import threading

# ===== الإعدادات =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("ضع TELEGRAM_TOKEN في إعدادات البيئة")

bot = telebot.TeleBot(TOKEN)

# ===== التخزين في الذاكرة =====
users = {}  # user_id -> {"name":.., "age":.., "gender":.., "respect":.., "profile_locked":False}
waiting_users = {}  # user_id -> {"topic":.., "gender_pref":..}
active_chats = {}  # user_id -> partner_id
chat_logs = {}  # user_id -> [last_50_messages]
warnings_sent = set()
banned_users = {}  # user_id -> ban_end_timestamp

# ===== قائمة الكلمات البذيئة =====
bad_words = [
"كس","كسمك","كسي","كسس","كسسس","كسسسس","كسمو","كصمك","اير","ايري","ايرنا","طيزنا","طيز",
"كسختك","يلعن ربك","يلعن دينك","يلعن روحك","عنربك","عندينك","يلعن شفراتك","قحبة","شرموطة",
"شلكة","منتاكة","سرموطة","قحب","شرموط","منيك","مكسكس"
]

# ===== دوال مساعدة =====
def get_penalty(respect, bad_count):
    """حساب الخصم الديناميكي حسب درجة الاحترام"""
    penalty = 0
    if respect >= 76:
        penalty = bad_count // 2   # كل كلمتين = نقطة
    elif 71 <= respect <= 75:
        penalty = bad_count        # كل كلمة = نقطة
    elif 61 <= respect <= 70:
        penalty = bad_count * 2
    elif 51 <= respect <= 60:
        penalty = bad_count * 3
    elif 41 <= respect <= 50:
        penalty = bad_count * 5
    elif 26 <= respect <= 40:
        penalty = bad_count * 10
    return penalty

def is_banned(user_id):
    if user_id in banned_users:
        if time.time() < banned_users[user_id]:
            return True
        else:
            del banned_users[user_id]
    return False

def add_message(user_id, text):
    if user_id not in chat_logs:
        chat_logs[user_id] = []
    chat_logs[user_id].append(text)
    if len(chat_logs[user_id]) > 50:
        chat_logs[user_id] = chat_logs[user_id][-50:]

# ===== لوحة الأزرار الدائمة =====
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🏠 الرئيسية"), KeyboardButton("👤 الملف الشخصي"), KeyboardButton("🔍 البحث"))
    return kb

# ===== البداية =====
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    if user_id not in users:
        users[user_id] = {"name": None, "age": None, "gender": None, "respect": 80, "profile_locked": False}
        bot.send_message(user_id, "👋 أهلاً! لنبدأ بإنشاء ملفك الشخصي.\nما اسمك؟", reply_markup=main_menu())
    else:
        bot.send_message(user_id, "مرحباً بعودتك!", reply_markup=main_menu())

# ===== الملف الشخصي =====
@bot.message_handler(func=lambda m: m.text == "👤 الملف الشخصي")
def profile_menu(msg):
    user = users.get(msg.from_user.id)
    if not user: return
    info = f"👤 الاسم: {user['name']}\n🎂 العمر: {user['age']}\n⚧️ الجنس: {user['gender']}\n⭐ الاحترام: {user['respect']}"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✏️ تعديل الاسم", "✏️ تعديل العمر", "✏️ تعديل الجنس")
    kb.add("⬅️ رجوع")
    bot.send_message(msg.chat.id, info, reply_markup=kb)

# ===== البحث =====
@bot.message_handler(func=lambda m: m.text == "🔍 البحث")
def search_menu(msg):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🧠 فلسفة", "⚽ رياضة")
    kb.add("☪️ دين", "🏛️ سياسة")
    kb.add("🤝 تعارف")
    kb.add("⬅️ رجوع")
    bot.send_message(msg.chat.id, "ماذا تريد أن تناقش اليوم؟ اختر مجال النقاش:", reply_markup=kb)

# ===== اختيار الجنس للمطابقة =====
@bot.message_handler(func=lambda m: m.text in ["🧠 فلسفة","⚽ رياضة","☪️ دين","🏛️ سياسة","🤝 تعارف"])
def topic_choice(msg):
    topic = msg.text
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(f"{topic} 👨", f"{topic} 👩")
    kb.add("⬅️ رجوع")
    bot.send_message(msg.chat.id, "اختر مع من تريد التحدث:", reply_markup=kb)

# ===== الإبلاغ =====
@bot.message_handler(func=lambda m: m.text == "🚨 إبلاغ")
def report_user(msg):
    user_id = msg.from_user.id
    if user_id not in active_chats:
        bot.send_message(user_id, "❌ لا يمكنك الإبلاغ بدون وجود دردشة.")
        return
    partner_id = active_chats[user_id]
    messages = chat_logs.get(partner_id, [])
    bad_count = sum(1 for m in messages for w in bad_words if w in m)
    penalty = get_penalty(users[partner_id]["respect"], bad_count)
    users[partner_id]["respect"] -= penalty
    bot.send_message(user_id, f"✅ تم الإبلاغ. عدد الكلمات البذيئة: {bad_count}\nالخصم: {penalty} نقاط.")
    bot.send_message(partner_id, "🚨 لقد تم الإبلاغ عنك! انتبه إلى سلوكك.")

# (تابع الكود: مطابقة، محادثة، مغادرة بعد 30 ثانية، الحظر، إلخ...)
bot.send_message(user_id, "لقد تم حظرك نهائياً من استخدام البوت بسبب تجاوز الحدود.")
            return

    # بعد حساب النقاط وتطبيق القوانين يتم حفظ الملف
    save_profiles()


# ===== دوال الأزرار الدائمة =====
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔍 البحث", "👤 الملف الشخصي", "🏠 الرئيسية")
    bot.send_message(user_id, "القائمة الرئيسية:", reply_markup=markup)


@bot.message_handler(func=lambda msg: msg.text == "🏠 الرئيسية")
def handle_home(msg):
    main_menu(msg.chat.id)


@bot.message_handler(func=lambda msg: msg.text == "👤 الملف الشخصي")
def handle_profile(msg):
    user_id = msg.chat.id
    profile = profiles.get(str(user_id))
    if profile:
        bot.send_message(user_id, f"👤 اسمك: {profile['name']}\n🎂 عمرك: {profile['age']}\n⚧ جنسك: {profile['gender']}\n💯 احترامك: {profile['respect']}")
    else:
        bot.send_message(user_id, "لم تقم بإنشاء ملف شخصي بعد. اضغط /start")


@bot.message_handler(func=lambda msg: msg.text == "🔍 البحث")
def handle_search(msg):
    user_id = msg.chat.id
    if str(user_id) not in profiles:
        bot.send_message(user_id, "قم بإنشاء ملف شخصي أولاً عبر /start")
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📚 فلسفة 🧑", "📚 فلسفة 👩")
    markup.add("⚽ رياضة 🧑", "⚽ رياضة 👩")
    markup.add("🕌 دين 🧑", "🕌 دين 👩")
    markup.add("🏛 سياسة 🧑", "🏛 سياسة 👩")
    markup.add("🤝 تعارف 🧑", "🤝 تعارف 👩")
    bot.send_message(user_id, "ماذا تريد أن تناقش اليوم؟ اختر المجال والجنس:", reply_markup=markup)
# ===== المطابقة بين المستخدمين =====
waiting_users = {  # { (topic, gender): [user_ids...] }
    ("فلسفة", "ذكر"): [],
    ("فلسفة", "أنثى"): [],
    ("رياضة", "ذكر"): [],
    ("رياضة", "أنثى"): [],
    ("دين", "ذكر"): [],
    ("دين", "أنثى"): [],
    ("سياسة", "ذكر"): [],
    ("سياسة", "أنثى"): [],
    ("تعارف", "ذكر"): [],
    ("تعارف", "أنثى"): [],
}

# سجل محادثات مؤقت (آخر 50 رسالة)
chat_history = {}  # {user_id: [("من", "النص"), ...]}


def add_to_history(user_id, sender, text):
    if user_id not in chat_history:
        chat_history[user_id] = []
    chat_history[user_id].append((sender, text))
    if len(chat_history[user_id]) > 50:
        chat_history[user_id] = chat_history[user_id][-50:]


@bot.message_handler(func=lambda msg: msg.text in [
    "📚 فلسفة 🧑", "📚 فلسفة 👩",
    "⚽ رياضة 🧑", "⚽ رياضة 👩",
    "🕌 دين 🧑", "🕌 دين 👩",
    "🏛 سياسة 🧑", "🏛 سياسة 👩",
    "🤝 تعارف 🧑", "🤝 تعارف 👩"
])
def handle_topic_choice(msg):
    user_id = msg.chat.id
    choice = msg.text

    # تحديد المجال والجنس المطلوب
    if "فلسفة" in choice: topic = "فلسفة"
    elif "رياضة" in choice: topic = "رياضة"
    elif "دين" in choice: topic = "دين"
    elif "سياسة" in choice: topic = "سياسة"
    else: topic = "تعارف"

    if "🧑" in choice: target_gender = "ذكر"
    else: target_gender = "أنثى"

    # البحث عن مستخدم آخر مطابق
    key = (topic, target_gender)
    opposite_gender = "أنثى" if profiles[str(user_id)]["gender"] == "ذكر" else "ذكر"

    # هل يوجد شخص في الانتظار من نفس الفئة لكن بالجنس الآخر؟
    partner_key = (topic, profiles[str(user_id)]["gender"])
    if waiting_users.get(partner_key) and waiting_users[partner_key]:
        partner_id = waiting_users[partner_key].pop(0)

        # تهنئة وعرض بيانات
        partner_profile = profiles[str(partner_id)]
        my_profile = profiles[str(user_id)]

        bot.send_message(user_id,
            f"🎉 تم إيجاد شريك!\n\n👤 الاسم: {partner_profile['name']}\n🎂 العمر: {partner_profile['age']}\n💯 الاحترام: {partner_profile['respect']}")
        bot.send_message(partner_id,
            f"🎉 تم إيجاد شريك!\n\n👤 الاسم: {my_profile['name']}\n🎂 العمر: {my_profile['age']}\n💯 الاحترام: {my_profile['respect']}")

        bot.send_message(user_id, "يمكنك بدء المحادثة الآن ✅")
        bot.send_message(partner_id, "يمكنك بدء المحادثة الآن ✅")

    else:
        waiting_users[key].append(user_id)
        bot.send_message(user_id, "⏳ لم يتم العثور على شريك حالياً، سيتم مطابقتك عند توفر شخص مناسب.")


# ===== زر الإبلاغ =====
@bot.message_handler(commands=["report"])
def handle_report(msg):
    user_id = msg.chat.id
    if user_id not in chat_history:
        bot.send_message(user_id, "لا يوجد محادثة للإبلاغ عنها.")
        return

    # استعراض آخر 50 رسالة
    history = chat_history[user_id]
    bad_count = sum(any(bad in text for bad in bad_words) for _, text in history)

    # خصم النقاط حسب المستوى
    if str(user_id) in profiles:
        apply_respect_penalty(user_id, bad_count)

    bot.send_message(user_id, "✅ تم إرسال البلاغ وسيتم اتخاذ الإجراءات المناسبة.")


# ===== التوجيه بين المستخدمين =====
@bot.message_handler(func=lambda msg: True)
def relay_messages(msg):
    user_id = msg.chat.id
    text = msg.text

    # حفظ الرسالة في السجل
    add_to_history(user_id, "me", text)

    # البحث عن شريك مرتبط
    for key, users in waiting_users.items():
        if user_id in users:
            # المستخدم ما زال ينتظر مطابقة
            return

    # إرسال الرسالة للطرف الآخر إن وجد
    for key, users in waiting_users.items():
        for uid in users:
            if uid == user_id:
                continue

    # مبدئياً (تطوير لاحق) — تحتاج إدارة جلسات نشطة
    # لتحديد من يتحدث مع من بالضبط
    # يمكن ربط user_id ↔ partner_id في dict منفصل active_chats


print("🤖 البوت يعمل...")
bot.polling()
# ===== إدارة الجلسات النشطة =====
active_chats = {}  # user_id -> partner_id
leave_timers = {}   # user_id -> وقت بدء المحادثة

# بعد المطابقة، أضف هذا الرابط بين الطرفين:
def start_chat(user_id, partner_id):
    active_chats[user_id] = partner_id
    active_chats[partner_id] = user_id
    leave_timers[user_id] = time.time()
    leave_timers[partner_id] = time.time()
    bot.send_message(user_id, "✅ تم بدء المحادثة! يمكنك التحدث الآن.")
    bot.send_message(partner_id, "✅ تم بدء المحادثة! يمكنك التحدث الآن.")

# إعادة توجيه الرسائل بين الشريكين
@bot.message_handler(func=lambda msg: True)
def relay(msg):
    user_id = msg.chat.id
    text = msg.text

    # تحقق من الحظر
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ أنت محظور من استخدام البوت حالياً.")
        return

    # إضافة الرسالة للسجل
    add_to_history(user_id, "me", text)

    # تحقق من وجود شريك نشط
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        sender_name = profiles[str(user_id)]["name"] if str(user_id) in profiles else "مستخدم"
        bot.send_message(partner_id, f"💬 {sender_name}: {text}")
    else:
        bot.send_message(user_id, "ℹ️ لا يوجد شريك نشط، اضغط 🔍 البحث للعثور على شريك.")

# ===== زر المغادرة =====
@bot.message_handler(func=lambda msg: msg.text == "❌ مغادرة 🚪")
def leave_chat(msg):
    user_id = msg.chat.id
    if user_id not in active_chats:
        bot.send_message(user_id, "ℹ️ أنت لست في محادثة حالياً.")
        return

    elapsed = time.time() - leave_timers.get(user_id, 0)
    if elapsed < 30:
        bot.send_message(user_id, f"⏳ لا يمكنك المغادرة قبل 30 ثانية. تبقى {int(30 - elapsed)} ثانية.")
        return

    # تأكيد المغادرة
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("تأكيد المغادرة 🚪", callback_data=f"confirm_leave_{user_id}"))
    bot.send_message(user_id, "هل تريد فعلاً المغادرة؟", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_leave_"))
def confirm_leave(call):
    user_id = int(call.data.split("_")[-1])
    if user_id not in active_chats:
        bot.answer_callback_query(call.id, "ℹ️ لا يوجد شريك للدردشة.")
        return

    partner_id = active_chats[user_id]
    bot.send_message(user_id, "🚪 غادرت الدردشة.")
    bot.send_message(partner_id, "🚪 شريكك غادر الدردشة.")
    # تنظيف البيانات
    for uid in [user_id, partner_id]:
        active_chats.pop(uid, None)
        leave_timers.pop(uid, None)
