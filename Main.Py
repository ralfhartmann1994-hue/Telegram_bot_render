import os
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ===== الإعدادات =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")  # ضع التوكن في متغير بيئة داخل Render
if not TOKEN:
    raise RuntimeError("ضع TELEGRAM_TOKEN في إعدادات البيئة على Render")

bot = telebot.TeleBot(TOKEN)

# ===== التخزين المؤقت في الذاكرة =====
users = {}  # تخزين بيانات المستخدمين
chats = {}  # إدارة المحادثات الجارية
reports = []  # بلاغات المستخدمين

# ===== قائمة الكلمات الممنوعة =====
bad_words = ["fuck", "shit", "bitch", "asshole", "dick", "pussy", "motherfucker",
             "لعنة", "زق", "قحبة", "كس", "نيك", "شرموط", "كلب", "حمار"]

# ===== هيكل بيانات المستخدم =====
def create_user(user_id):
    return {
        "name": None,
        "age": None,
        "gender": None,   # لا يتغير بعد التسجيل
        "topic": None,
        "respect": 80,
        "warnings": 0,
        "banned_until": None,
        "chat_partner": None,
        "messages": []
    }

# ===== أوامر البداية =====
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = create_user(user_id)
        bot.send_message(user_id,
                         "👋 أهلاً بك في بوت الدردشة الذكي!\n\n"
                         "سيتم إنشاء ملفك الشخصي أولاً.\n"
                         "ما هو اسمك؟")
        bot.register_next_step_handler(message, set_name)
    else:
        bot.send_message(user_id, "أهلاً بك مجدداً! ✅\nاستخدم /menu لعرض الخيارات.")

# ===== تسجيل المستخدم =====
def set_name(message):
    user_id = message.from_user.id
    name = message.text.strip()
    if not name or len(name) < 2:
        bot.send_message(user_id, "⚠️ الاسم قصير جداً، أعد المحاولة:")
        return bot.register_next_step_handler(message, set_name)
    users[user_id]["name"] = name
    bot.send_message(user_id, "📅 ممتاز! الآن أدخل عمرك:")
    bot.register_next_step_handler(message, set_age)

def set_age(message):
    user_id = message.from_user.id
    try:
        age = int(message.text.strip())
        if age < 10 or age > 100:
            raise ValueError
        users[user_id]["age"] = age
        # الجنس يُطلب مرة واحدة فقط
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("👨 ذكر", "👩 أنثى")
        bot.send_message(user_id, "👤 اختر جنسك (لا يمكن تغييره لاحقاً):", reply_markup=markup)
        bot.register_next_step_handler(message, set_gender)
    except ValueError:
        bot.send_message(user_id, "⚠️ أدخل عمرك كعدد صحيح (10-100):")
        bot.register_next_step_handler(message, set_age)

def set_gender(message):
    user_id = message.from_user.id
    gender = message.text.strip()
    if gender not in ["👨 ذكر", "👩 أنثى"]:
        bot.send_message(user_id, "⚠️ اختر من الأزرار فقط:")
        return bot.register_next_step_handler(message, set_gender)
    users[user_id]["gender"] = gender
    # اختيار الفئة
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("💭 فلسفة", "🙏 دين", "🏛️ سياسة", "🤝 تعارف", "⚽ رياضة")
    bot.send_message(user_id, "اختر فئة النقاش التي تفضلها:", reply_markup=markup)
    bot.register_next_step_handler(message, set_topic)

def set_topic(message):
    user_id = message.from_user.id
    topic = message.text.strip()
    if topic not in ["💭 فلسفة", "🙏 دين", "🏛️ سياسة", "🤝 تعارف", "⚽ رياضة"]:
        bot.send_message(user_id, "⚠️ اختر من الأزرار فقط:")
        return bot.register_next_step_handler(message, set_topic)
    users[user_id]["topic"] = topic
    bot.send_message(user_id, "✅ تم إنشاء ملفك الشخصي بنجاح!\n"
                              "استخدم /menu لعرض الخيارات.", reply_markup=ReplyKeyboardRemove())

# ===== القائمة الرئيسية =====
@bot.message_handler(commands=["menu"])
def menu(message):
    user_id = message.from_user.id
    if user_id not in users or not users[user_id]["topic"]:
        return bot.send_message(user_id, "⚠️ يجب إكمال التسجيل أولاً عبر /start")

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 عرض ملفي", "✏️ تعديل الاسم/العمر")
    markup.add("🔎 البحث عن دردشة")
    bot.send_message(user_id, "📌 القائمة الرئيسية:", reply_markup=markup)

# ===== عرض الملف الشخصي =====
@bot.message_handler(func=lambda m: m.text == "👤 عرض ملفي")
def show_profile(message):
    user_id = message.from_user.id
    u = users[user_id]
    bot.send_message(user_id,
                     f"👤 الاسم: {u['name']}\n"
                     f"📅 العمر: {u['age']}\n"
                     f"{u['gender']}\n"
                     f"🎯 الفئة: {u['topic']}\n"
                     f"💯 درجة الاحترام: {u['respect']}")

# ===== تعديل الاسم والعمر =====
@bot.message_handler(func=lambda m: m.text == "✏️ تعديل الاسم/العمر")
def edit_profile(message):
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("✏️ تعديل الاسم", "✏️ تعديل العمر")
    bot.send_message(message.chat.id, "ماذا تريد تعديل؟", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "✏️ تعديل الاسم")
def edit_name(message):
    user_id = message.from_user.id
    bot.send_message(user_id, "أدخل اسمك الجديد:")
    bot.register_next_step_handler(message, save_new_name)

def save_new_name(message):
    user_id = message.from_user.id
    name = message.text.strip()
    if not name or len(name) < 2:
        bot.send_message(user_id, "⚠️ الاسم غير صالح.")
        return
    users[user_id]["name"] = name
    bot.send_message(user_id, "✅ تم تعديل الاسم بنجاح.")

@bot.message_handler(func=lambda m: m.text == "✏️ تعديل العمر")
def edit_age(message):
    user_id = message.from_user.id
    bot.send_message(user_id, "أدخل عمرك الجديد:")
    bot.register_next_step_handler(message, save_new_age)

def save_new_age(message):
    user_id = message.from_user.id
    try:
        age = int(message.text.strip())
        if age < 10 or age > 100:
            raise ValueError
        users[user_id]["age"] = age
        bot.send_message(user_id, "✅ تم تعديل العمر بنجاح.")
    except ValueError:
        bot.send_message(user_id, "⚠️ العمر غير صالح.")

# ===== البحث عن دردشة (المطابقة) =====
@bot.message_handler(func=lambda m: m.text == "🔎 البحث عن دردشة")
def search_chat(message):
    user_id = message.from_user.id
    topic = users[user_id]["topic"]
    for uid, u in users.items():
        if uid != user_id and u["topic"] == topic and u["chat_partner"] is None:
            # مطابقة
            users[user_id]["chat_partner"] = uid
            users[uid]["chat_partner"] = user_id
            chats[(user_id, uid)] = []
            intro1 = (f"🎉 تم العثور على شريك دردشة!\n"
                      f"👤 {u['name']} ({u['age']} سنة)\n{u['gender']}\n"
                      f"💯 احترامه: {u['respect']}")
            intro2 = (f"🎉 تم العثور على شريك دردشة!\n"
                      f"👤 {users[user_id]['name']} ({users[user_id]['age']} سنة)\n"
                      f"{users[user_id]['gender']}\n"
                      f"💯 احترامه: {users[user_id]['respect']}")
            leave_btn = ReplyKeyboardMarkup(resize_keyboard=True)
            leave_btn.add("🚨 إبلاغ", "🚪 مغادرة")
            bot.send_message(user_id, intro1, reply_markup=leave_btn)
            bot.send_message(uid, intro2, reply_markup=leave_btn)
            return
    bot.send_message(user_id, "⌛ لا يوجد شريك متاح الآن، حاول لاحقاً.")

# ===== إدارة الرسائل بين الشركاء =====
@bot.message_handler(func=lambda m: True)
def relay_messages(message):
    user_id = message.from_user.id
    if user_id not in users or not users[user_id]["chat_partner"]:
        return

    partner_id = users[user_id]["chat_partner"]

    # تحقق الكلمات البذيئة
    lower_msg = message.text.lower()
    if any(bad in lower_msg for bad in bad_words):
        users[user_id]["warnings"] += 1
        users[user_id]["respect"] -= 5 + users[user_id]["warnings"]
        if users[user_id]["respect"] <= 25:
            bot.send_message(user_id, "⛔ تم حظرك نهائياً بسبب تكرار الألفاظ البذيئة.")
            users[user_id]["chat_partner"] = None
            users[partner_id]["chat_partner"] = None
            return
        elif users[user_id]["respect"] <= 40:
            users[user_id]["banned_until"] = time.time() + 7 * 24 * 3600
            bot.send_message(user_id, "⏳ تم حظرك جزئياً لمدة أسبوع.")
            return

    # حفظ الرسائل (آخر 50 فقط)
    chats[(user_id, partner_id)] = chats.get((user_id, partner_id), [])[-49:] + [message.text]

    # إعادة إرسال الرسالة للطرف الآخر
    bot.send_message(partner_id, f"{users[user_id]['name']} 💬: {message.text}")

# ===== تشغيل البوت =====
try:
    print("🤖 Bot is running...")
    bot.infinity_polling(skip_pending=True)
except Exception as e:
    print(f"❌ Bot stopped due to: {e}") 
