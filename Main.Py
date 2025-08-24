import os
import time
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ===== الإعدادات =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("ضع TELEGRAM_TOKEN في إعدادات البيئة على Render")

bot = telebot.TeleBot(TOKEN)

# ===== التخزين المؤقت في الذاكرة =====
users = {}
active_chats = {}
leave_timers = {}

TOPICS = ["📚 فلسفة", "⚽ رياضة", "☪️ دين", "🗳️ سياسة", "🤝 تعارف"]
GENDER_BTNS = ["👨 ذكر", "👩 أنثى"]
SEARCH_TIMEOUT = 3600  # ثانية = 1 ساعة

# ===== أدوات مساعدة =====
def get_respect_badge(score: int) -> str:
    if score >= 80:
        return "🌟"
    if score >= 60:
        return "🙂"
    if score >= 40:
        return "⚠️"
    return "🚫"

def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🏠 الرئيسية"))
    kb.add(KeyboardButton("📊 ملفي"))
    kb.add(KeyboardButton("🔍 بحث"))
    return kb

# ===== البداية =====
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.chat.id
    users.setdefault(uid, {
        "name": message.from_user.first_name or "",
        "gender": None,
        "age": None,
        "respect": 80,
        "gender_changes": 0,
        "step": "gender",
        "topic": None
    })
    bot.send_message(uid, "👋 مرحبًا! ما هو جنسك؟", 
                     reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(*[KeyboardButton(g) for g in GENDER_BTNS]))

# ===== التعامل مع الأزرار الرئيسية =====
@bot.message_handler(func=lambda m: m.text in ["🏠 الرئيسية", "📊 ملفي", "🔍 بحث"])
def main_buttons(message):
    uid = message.chat.id
    if message.text == "📊 ملفي":
        my_profile(message)
    elif message.text == "🔍 بحث":
        choose_topic(message)
    elif message.text == "🏠 الرئيسية":
        bot.send_message(uid, "👋 أنت في الصفحة الرئيسية.", reply_markup=main_menu(uid))

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
    bot.send_message(uid, "✅ تم حفظ ملفك الشخصي!", reply_markup=main_menu(uid))

# ===== عرض الملف الشخصي =====
def my_profile(message):
    uid = message.chat.id
    u = users.get(uid)
    if not u:
        return bot.send_message(uid, "ℹ️ ابدأ أولاً عبر /start")
    badge = get_respect_badge(u.get("respect", 80))
    bot.send_message(uid,
        f"📊 ملفك الشخصي:\n"
        f"• الاسم: {u.get('name') or '—'}\n"
        f"• الجنس: {u.get('gender') or '—'}\n"
        f"• العمر: {u.get('age') or '—'}\n"
        f"• درجة الاحترام: {u.get('respect', 80)} {badge}\n\n"
        f"اختر من الأزرار أدناه أو ابدأ البحث عن شريك.",
        reply_markup=main_menu(uid)
    )

# ===== اختيار موضوع الدردشة =====
@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") is None)
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

# ===== البحث والمطابقة الطويلة =====
def find_partner(uid):
    start_time = time.time()
    my_topic = users[uid].get("topic")
    desired_gender = users[uid].get("desired_gender")
    while True:
        for other_id, data in users.items():
            if other_id == uid or other_id in active_chats or uid in active_chats:
                continue
            if data.get("topic") == my_topic and data.get("gender") == desired_gender:
                active_chats[uid] = other_id
                active_chats[other_id] = uid
                leave_timers[uid] = time.time()
                leave_timers[other_id] = time.time()
                kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("❌ مغادرة 🚪"))
                bot.send_message(other_id, "✅ تم العثور على شريك! 🎉 ابدأوا الحديث الآن.", reply_markup=kb)
                bot.send_message(uid, "✅ تم العثور على شريك! 🎉 ابدأ الحديث الآن.", reply_markup=kb)
                return
        if time.time() - start_time > SEARCH_TIMEOUT:
            bot.send_message(uid, "⌛ لم يتم العثور على شريك بعد ساعة من البحث، حاول لاحقًا.", reply_markup=main_menu(uid))
            return
        time.sleep(5)

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "search_gender")
def do_search(message):
    uid = message.chat.id
    choice = message.text
    if choice not in ["🔍 البحث عن رجل 👨", "🔍 البحث عن فتاة 👩"]:
        return bot.send_message(uid, "❌ اختر من الأزرار فقط.")
    users[uid]["desired_gender"] = "ذكر" if "رجل" in choice else "أنثى"
    users[uid]["step"] = None
    bot.send_message(uid, "🔍 جاري البحث عن شريك...")
    threading.Thread(target=find_partner, args=(uid,)).start()

# ===== مغادرة الدردشة مع مؤقت 30 ثانية =====
@bot.message_handler(func=lambda m: m.text == "❌ مغادرة 🚪")
def leave_chat(message):
    uid = message.chat.id
    if uid not in active_chats:
        return bot.send_message(uid, "ℹ️ أنت لست في محادثة حالياً.")
    
    elapsed = time.time() - leave_timers.get(uid, 0)
    if elapsed < 30:
        remaining = int(30 - elapsed)
        return bot.send_message(uid, f"⏳ لا يمكنك المغادرة قبل 30 ثانية. انتظر {remaining} ثانية.")

    partner = active_chats[uid]
    bot.send_message(partner, "🚪 غادر شريكك الدردشة.")
    bot.send_message(uid, "🚪 غادرت الدردشة. اختر 🔍 بحث للبدء من جديد.", reply_markup=main_menu(uid))

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
            bot.send_message(uid, "ℹ️ اختر 🔍 بحث للبدء.")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
