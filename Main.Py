import os
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ===== الإعدادات =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("ضع TELEGRAM_TOKEN في إعدادات البيئة")

bot = telebot.TeleBot(TOKEN)

# ===== التخزين في الذاكرة =====
users = {}  # user_id -> {"name":.., "age":.., "gender":.., "respect":.., "gender_changes":0, "profile_locked":False}
waiting_users = { (topic, gender): [] for topic in ["فلسفة","رياضة","دين","سياسة","تعارف"] for gender in ["ذكر","أنثى"] }
active_chats = {}  # user_id -> partner_id
chat_logs = {}  # user_id -> [last 50 messages]
leave_timers = {}  # user_id -> وقت بدء المحادثة
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
    penalty = 0
    if respect >= 76:
        penalty = bad_count // 2
    elif 71 <= respect <= 75:
        penalty = bad_count
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

# ===== لوحة الأزرار الرئيسية =====
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🏠 الرئيسية"), KeyboardButton("👤 الملف الشخصي"), KeyboardButton("🔍 البحث"))
    return kb

# ===== البداية =====
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    if user_id not in users:
        users[user_id] = {"name": None, "age": None, "gender": None, "respect": 80, "gender_changes": 0, "profile_locked": False}
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

# ===== تعديل البيانات =====
@bot.message_handler(func=lambda m: m.text in ["✏️ تعديل الاسم", "✏️ تعديل العمر", "✏️ تعديل الجنس"])
def edit_profile(msg):
    user_id = msg.from_user.id
    if msg.text == "✏️ تعديل الاسم":
        bot.send_message(user_id, "اكتب الاسم الجديد:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True))
    elif msg.text == "✏️ تعديل العمر":
        bot.send_message(user_id, "اكتب العمر الجديد كرقم:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True))
    elif msg.text == "✏️ تعديل الجنس":
        if users[user_id]["gender_changes"] >= 1:
            bot.send_message(user_id, "🚫 لا يمكنك تغيير الجنس أكثر من مرة.")
            return
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("👨 ذكر", "👩 أنثى")
        bot.send_message(user_id, "اختر الجنس الجديد:", reply_markup=kb)

# ===== البحث =====
TOPICS = ["📚 فلسفة","⚽ رياضة","☪️ دين","🏛 سياسة","🤝 تعارف"]

@bot.message_handler(func=lambda m: m.text == "🔍 البحث")
def search_menu(msg):
    user_id = msg.from_user.id
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in TOPICS:
        kb.add(t)
    kb.add("⬅️ رجوع")
    bot.send_message(user_id, "ماذا تريد أن تناقش اليوم؟ اختر مجال النقاش:", reply_markup=kb)

# ===== اختيار الجنس للمطابقة =====
@bot.message_handler(func=lambda m: m.text in TOPICS)
def topic_choice(msg):
    topic = msg.text
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(f"{topic} 👨", f"{topic} 👩")
    kb.add("⬅️ رجوع")
    bot.send_message(msg.chat.id, "اختر مع من تريد التحدث:", reply_markup=kb)

# ===== الإبلاغ =====
def check_respect_and_ban(user_id):
    respect = users[user_id]["respect"]
    if respect <= 25:
        banned_users[user_id] = float('inf')  # حظر دائم
        bot.send_message(user_id, "⛔ تم حظرك نهائياً من البوت بسبب انخفاض الاحترام تحت الحد المسموح.")
        return True
    elif respect <= 40:
        if user_id not in warnings_sent:
            banned_users[user_id] = time.time() + 7*24*3600  # أسبوع حظر مؤقت
            bot.send_message(user_id,
                "⚠️ تحذير شديد! احترامك وصل 40.\n"
                "لقد تم حظرك لمدة أسبوع بسبب سلوك غير لائق.\n"
                "تعلم من هذه التجربة وكن أكثر أخلاقًا عند استخدام البوت.\n"
                "إذا استمر السلوك السلبي، سيتم الحظر النهائي عند 25 نقطة.")
            warnings_sent.add(user_id)
            return True
    elif respect <= 50:
        if user_id not in warnings_sent:
            bot.send_message(user_id,
                "⚠️ تحذير! احترامك وصل 50.\n"
                "يجب أن تكون أكثر تهذيبًا عند الحديث.\n"
                "كل سلوك سيء إضافي سيخصم نقاط أكثر وقد يؤدي إلى الحظر المؤقت أو النهائي.\n"
                "نصائح: استخدم لغة محترمة، لا تسب أو تهين، وحافظ على مستوى النقاش راقيًا.")
            warnings_sent.add(user_id)
    return False

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
    check_respect_and_ban(partner_id)

# ===== المطابقة =====
def start_chat(user_id, partner_id):
    active_chats[user_id] = partner_id
    active_chats[partner_id] = user_id
    leave_timers[user_id] = time.time()
    leave_timers[partner_id] = time.time()
    bot.send_message(user_id, "✅ تم بدء المحادثة! يمكنك التحدث الآن.")
    bot.send_message(partner_id, "✅ تم بدء المحادثة! يمكنك التحدث الآن.")

@bot.message_handler(func=lambda msg: any(t in msg.text for t in TOPICS))
def handle_topic_gender_choice(msg):
    user_id = msg.chat.id
    text = msg.text
    topic = None
    gender_pref = "ذكر" if "👨" in text else "أنثى"
    for t in ["فلسفة","رياضة","دين","سياسة","تعارف"]:
        if t in text:
            topic = t
            break
    if topic is None: return
    opposite_gender = "أنثى" if users[user_id]["gender"] == "ذكر" else "ذكر"
    key = (topic, opposite_gender)
    if waiting_users[key]:
        partner_id = waiting_users[key].pop(0)
        start_chat(user_id, partner_id)
        bot.send_message(user_id, f"🎉 تم إيجاد شريك!\n👤 الاسم: {users[partner_id]['name']}\n🎂 العمر: {users[partner_id]['age']}\n⭐ الاحترام: {users[partner_id]['respect']}")
        bot.send_message(partner_id, f"🎉 تم إيجاد شريك!\n👤 الاسم: {users[user_id]['name']}\n🎂 العمر: {users[user_id]['age']}\n⭐ الاحترام: {users[user_id]['respect']}")
    else:
        waiting_users[(topic, users[user_id]["gender"])].append(user_id)
        bot.send_message(user_id, "⏳ لم يتم العثور على شريك حالياً، سيتم مطابقتك عند توفر شخص مناسب.")

# ===== إعادة توجيه الرسائل بين الشريكين =====
@bot.message_handler(func=lambda msg: True)
def relay(msg):
    user_id = msg.chat.id
    text = msg.text
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ أنت محظور من استخدام البوت حالياً.")
        return
    add_message(user_id, text)

    # خصم نقاط الكلمات البذيئة تلقائياً أثناء الحديث
    bad_count = sum(1 for w in bad_words if w in text)
    if bad_count > 0:
        users[user_id]["respect"] -= get_penalty(users[user_id]["respect"], bad_count)
        check_respect_and_ban(user_id)

    if user_id in active_chats:
        partner_id = active_chats[user_id]
        sender_name = users[user_id]["name"] or "مستخدم"
        bot.send_message(partner_id, f"💬 {sender_name}: {text}")
    else:
        bot.send_message(user_id, "ℹ️ لا يوجد شريك نشط، اضغط 🔍 البحث للعثور على شريك.")

# ===== زر المغادرة بعد 30 ثانية =====
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
    for uid in [user_id, partner_id]:
        active_chats.pop(uid, None)
        leave_timers.pop(uid, None)

print("🤖 البوت يعمل...")
bot.infinity_polling(skip_pending=True)
