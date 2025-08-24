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
users = {}            # user_id -> {name, gender, age, respect, gender_changes, step, topic}
active_chats = {}     # user_id -> partner_id
leave_timers = {}     # user_id -> timestamp when chat started

TOPICS = ["📚 فلسفة", "⚽ رياضة", "☪️ دين", "🗳️ سياسة", "🤝 تعارف"]
GENDER_BTNS = ["👨 ذكر", "👩 أنثى"]

# ===== أدوات مساعدة =====
def get_respect_badge(score: int) -> str:
    if score >= 80:
        return "🌟"
    if score >= 60:
        return "🙂"
    if score >= 40:
        return "⚠️"
    return "🚫"

# ===== البداية =====
@bot.message_handler(commands=["start"])  # /start
def start(message):
    uid = message.chat.id
    users.setdefault(uid, {
        "name": message.from_user.first_name or "" ,
        "gender": None,
        "age": None,
        "respect": 80,
        "gender_changes": 0,
        "step": "gender",
        "topic": None
    })
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENDER_BTNS:
        kb.add(KeyboardButton(g))
    bot.send_message(uid, "👋 مرحبًا! ما هو جنسك؟", reply_markup=kb)

# ===== تحديد الجنس =====
@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "gender")
def set_gender(message):
    uid = message.chat.id
    txt = message.text
    if txt not in GENDER_BTNS:
        return bot.send_message(uid, "❌ اختر من الأزرار فقط.")
    users[uid]["gender"] = "ذكر" if "ذكر" in txt else "أنثى"
    users[uid]["step"] = "age"
    bot.send_message(uid, "🎂 كم عمرك؟", reply_markup=ReplyKeyboardRemove())

# ===== تحديد العمر =====
@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "age")
def set_age(message):
    uid = message.chat.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ الرجاء إدخال العمر كرقم.")
    users[uid]["age"] = int(message.text)
    users[uid]["step"] = None
    bot.send_message(uid, "✅ تم حفظ ملفك الشخصي!\nاكتب 👉 /بحث للبدء أو 👉 /ملفي لعرض بياناتك.")

# ===== عرض الملف الشخصي =====
@bot.message_handler(commands=["ملفي"])  # /ملفي
def my_profile(message):
    uid = message.chat.id
    u = users.get(uid)
    if not u:
        return bot.send_message(uid, "ℹ️ اكتب /start أولاً.")
    badge = get_respect_badge(u.get("respect", 80))
    bot.send_message(uid,
        f"📊 ملفك الشخصي:\n"
        f"• الاسم: {u.get('name') or '—'}\n"
        f"• الجنس: {u.get('gender') or '—'}\n"
        f"• العمر: {u.get('age') or '—'}\n"
        f"• درجة الاحترام: {u.get('respect', 80)} {badge}\n\n"
        f"اكتب /تعديل لتعديل البيانات أو /بحث للعثور على شريك.")

# ===== تعديل البيانات =====
@bot.message_handler(commands=["تعديل"])  # /تعديل
def edit_menu(message):
    uid = message.chat.id
    if uid not in users:
        return bot.send_message(uid, "ℹ️ اكتب /start أولاً.")
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✏️ تعديل الاسم"))
    kb.add(KeyboardButton("🎂 تعديل العمر"))
    kb.add(KeyboardButton("🚻 تعديل الجنس"))
    users[uid]["step"] = "edit_menu"
    bot.send_message(uid, "🛠️ ماذا تريد أن تعدل؟", reply_markup=kb)

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "edit_menu")
def handle_edit_choice(message):
    uid = message.chat.id
    choice = message.text
    if choice == "✏️ تعديل الاسم":
        users[uid]["step"] = "edit_name"
        bot.send_message(uid, "اكتب الاسم الجديد:", reply_markup=ReplyKeyboardRemove())
    elif choice == "🎂 تعديل العمر":
        users[uid]["step"] = "edit_age"
        bot.send_message(uid, "اكتب العمر الجديد كرقم:", reply_markup=ReplyKeyboardRemove())
    elif choice == "🚻 تعديل الجنس":
        # مسموح مرة واحدة فقط
        if users[uid].get("gender_changes", 0) >= 1:
            return bot.send_message(uid, "🚫 عذرًا، لا يمكنك تغيير الجنس أكثر من مرة. المصداقية مهمة عندنا ❤️")
        # تحذير لطيف
        bot.send_message(uid, "😅 إذا كنت ذكر خليك ذكر، لا تتحول رجاءً.. فريقنا ناقص 😂")
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for g in GENDER_BTNS:
            kb.add(KeyboardButton(g))
        users[uid]["step"] = "edit_gender"
        bot.send_message(uid, "اختر الجنس:", reply_markup=kb)
    else:
        bot.send_message(uid, "❌ اختر من الأزرار فقط.")

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "edit_name")
def do_edit_name(message):
    uid = message.chat.id
    users[uid]["name"] = message.text.strip()[:64]
    users[uid]["step"] = None
    bot.send_message(uid, "✅ تم تحديث الاسم.", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "edit_age")
def do_edit_age(message):
    uid = message.chat.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ الرجاء إدخال العمر كرقم.")
    users[uid]["age"] = int(message.text)
    users[uid]["step"] = None
    bot.send_message(uid, "✅ تم تحديث العمر.", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "edit_gender")
def do_edit_gender(message):
    uid = message.chat.id
    txt = message.text
    if txt not in GENDER_BTNS:
        return bot.send_message(uid, "❌ اختر من الأزرار فقط.")
    users[uid]["gender"] = "ذكر" if "ذكر" in txt else "أنثى"
    users[uid]["gender_changes"] = users[uid].get("gender_changes", 0) + 1
    users[uid]["step"] = None
    bot.send_message(uid, "✅ تم تحديث الجنس.", reply_markup=ReplyKeyboardRemove())

# ===== البحث والمطابقة =====
@bot.message_handler(commands=["بحث"])  # /بحث
def choose_topic(message):
    uid = message.chat.id
    u = users.get(uid)
    if not u or not u.get("gender") or not u.get("age"):
        return bot.send_message(uid, "ℹ️ أكمل ملفك أولاً عبر /start")
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in TOPICS:
        kb.add(KeyboardButton(t))
    users[uid]["step"] = "topic"
    bot.send_message(uid, "💬 عن ماذا تريد أن تتحدث اليوم؟", reply_markup=kb)

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "topic")
def topic_selected(message):
    uid = message.chat.id
    if message.text not in TOPICS:
        return bot.send_message(uid, "❌ اختر من القائمة فقط.")
    users[uid]["topic"] = message.text
    users[uid]["step"] = "search_gender"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔍 البحث عن رجل 👨"))
    kb.add(KeyboardButton("🔍 البحث عن فتاة 👩"))
    bot.send_message(uid, "👥 اختر نوع الشريك:", reply_markup=kb)

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "search_gender")
def do_search(message):
    uid = message.chat.id
    choice = message.text
    if choice not in ["🔍 البحث عن رجل 👨", "🔍 البحث عن فتاة 👩"]:
        return bot.send_message(uid, "❌ اختر من الأزرار فقط.")
    desired_gender = "ذكر" if "رجل" in choice else "أنثى"
    my_topic = users[uid]["topic"]

    # ابحث عن شريك مناسب
    for other_id, data in users.items():
        if other_id == uid:
            continue
        if other_id in active_chats or uid in active_chats:
            continue
        if data.get("topic") == my_topic and data.get("gender") == desired_gender:
            # طابق الاثنين
            active_chats[uid] = other_id
            active_chats[other_id] = uid
            leave_timers[uid] = time.time()
            leave_timers[other_id] = time.time()

            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(KeyboardButton("❌ مغادرة 🚪"))
            bot.send_message(other_id, "✅ تم العثور على شريك! 🎉 ابدأوا الحديث الآن.", reply_markup=kb)
            bot.send_message(uid, "✅ تم العثور على شريك! 🎉 ابدأ الحديث الآن.", reply_markup=kb)
            users[uid]["step"] = None
            users[other_id]["step"] = None
            return

    bot.send_message(uid, "🔍 لم يتم العثور على شريك حالياً، حاول لاحقًا.")

# ===== مغادرة الدردشة =====
@bot.message_handler(func=lambda m: m.text == "❌ مغادرة 🚪")
def leave_chat(message):
    uid = message.chat.id
    if uid not in active_chats:
        return bot.send_message(uid, "ℹ️ أنت لست في محادثة حالياً.")
    if time.time() - leave_timers.get(uid, 0) < 30:
        return bot.send_message(uid, "⏳ عليك الانتظار 30 ثانية قبل مغادرة الدردشة.")

    partner = active_chats[uid]
    bot.send_message(partner, "🚪 غادر شريكك الدردشة.")
    bot.send_message(uid, "🚪 غادرت الدردشة. اكتب 👉 /بحث للبدء من جديد.", reply_markup=ReplyKeyboardRemove())

    # نظّف الربط للطرفين
    for x in (uid, partner):
        active_chats.pop(x, None)
        leave_timers.pop(x, None)

# ===== تحويل الرسائل بين الشريكين =====
@bot.message_handler(func=lambda m: True)
def relay(message):
    uid = message.chat.id
    if uid in active_chats:
        partner = active_chats[uid]
        sender_name = users.get(uid, {}).get("name") or "مستخدم"
        bot.send_message(partner, f"💬 {sender_name}: {message.text}")
    else:
        u = users.get(uid)
        if u and u.get("step") is None:
            bot.send_message(uid, "ℹ️ اكتب 👉 /بحث للبدء.")

# ===== تشغيل البوت (Polling) =====
if __name__ == "__main__":
    # infinity_polling مناسبة للسيرفرات
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
