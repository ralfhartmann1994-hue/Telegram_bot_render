import os
import time
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import random

# ===== الإعدادات =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("ضع TELEGRAM_TOKEN في إعدادات البيئة على Render")

bot = telebot.TeleBot(TOKEN)

# ===== التخزين المؤقت في الذاكرة =====
users = {}            # بيانات المستخدمين
active_chats = {}     # user_id -> partner_id
leave_timers = {}     # user_id -> وقت بدء الدردشة
chat_history = {}     # user_id -> قائمة الرسائل الأخيرة (50 رسالة)
SEARCH_TIMEOUT = 3600  # 1 ساعة بحث
BAD_WORDS = [
    "كس","كسمك","كسي","كسس","كسسس","كسسسس","كسمو","كصمك","اير","ايري","ايرنا",
    "طيزنا","طيز","كسختك","يلعن ربك","يلعن دينك","يلعن روحك","عنربك","عندينك",
    "يلعن شفراتك","قحبة","شرموطة","شلكة","منتاكة","سرموطة","قحب","شرموط","منيك","مكسكس"
]

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

def send_delayed(uid, text, delay=None):
    time.sleep(delay if delay else random.uniform(0.5, 1))
    bot.send_message(uid, text)

# ===== البداية =====
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.chat.id
    if uid not in users:
        users[uid] = {
            "name": message.from_user.first_name or "",
            "gender": None,
            "age": None,
            "respect": 80,
            "gender_changes": 0,
            "step": "gender",
            "topic": None,
            "bad_words_count": 0
        }
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(*[KeyboardButton(g) for g in ["👨 ذكر", "👩 أنثى"]])
        send_delayed(uid, "👋 مرحبًا! ما هو جنسك؟", 0.5)
    else:
        send_delayed(uid, "🔍 بدء البحث عن شريك...", 0.5)
        choose_topic(message)

# ===== التعامل مع الأزرار الرئيسية =====
@bot.message_handler(func=lambda m: m.text in ["🏠 الرئيسية", "📊 ملفي", "🔍 بحث"])
def main_buttons(message):
    uid = message.chat.id
    if message.text == "📊 ملفي":
        my_profile(message)
    elif message.text == "🔍 بحث" or message.text == "🏠 الرئيسية":
        choose_topic(message)

# ===== تحديد الجنس =====
@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "gender")
def set_gender(message):
    uid = message.chat.id
    txt = message.text
    if txt not in ["👨 ذكر", "👩 أنثى"]:
        send_delayed(uid, "❌ اختر من الأزرار فقط.", 0.5)
        return
    users[uid]["gender"] = "ذكر" if "ذكر" in txt else "أنثى"
    users[uid]["step"] = "age"
    send_delayed(uid, "🎂 كم عمرك؟", 0.5,)

# ===== تحديد العمر =====
@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "age")
def set_age(message):
    uid = message.chat.id
    if not message.text.isdigit():
        send_delayed(uid, "⚠️ الرجاء إدخال العمر كرقم.", 0.5)
        return
    users[uid]["age"] = int(message.text)
    users[uid]["step"] = None
    send_delayed(uid, "✅ تم حفظ ملفك الشخصي!", 0.5)
    send_delayed(uid, "🔍 بدء البحث عن شريك...", 0.5)
    choose_topic(message)

# ===== عرض الملف الشخصي =====
def my_profile(message):
    uid = message.chat.id
    u = users.get(uid)
    if not u:
        send_delayed(uid, "ℹ️ ابدأ أولاً عبر /start", 0.5)
        return
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
def choose_topic(message):
    uid = message.chat.id
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in ["📚 فلسفة", "⚽ رياضة", "☪️ دين", "🗳️ سياسة", "🤝 تعارف"]:
        kb.add(KeyboardButton(t))
    users[uid]["step"] = "topic"
    send_delayed(uid, "💬 عن ماذا تريد أن تتحدث اليوم؟", 0.5)
    bot.send_message(uid, "اختر الموضوع:", reply_markup=kb)

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "topic")
def topic_selected(message):
    uid = message.chat.id
    if message.text not in ["📚 فلسفة", "⚽ رياضة", "☪️ دين", "🗳️ سياسة", "🤝 تعارف"]:
        send_delayed(uid, "❌ اختر من القائمة فقط.", 0.5)
        return
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
                chat_history[uid] = []
                chat_history[other_id] = []
                kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("❌ مغادرة 🚪"), KeyboardButton("🚨 إبلاغ"))
                send_delayed(other_id, "✅ تم العثور على شريك! 🎉 ابدأوا الحديث الآن.", 0.5)
                bot.send_message(uid, "✅ تم العثور على شريك! 🎉 ابدأ الحديث الآن.", reply_markup=kb)
                return
        if time.time() - start_time > SEARCH_TIMEOUT:
            send_delayed(uid, "⌛ لم يتم العثور على شريك بعد ساعة من البحث، حاول لاحقًا.", 0.5)
            return
        time.sleep(5)

@bot.message_handler(func=lambda m: users.get(m.chat.id, {}).get("step") == "search_gender")
def do_search(message):
    uid = message.chat.id
    choice = message.text
    if choice not in ["🔍 البحث عن رجل 👨", "🔍 البحث عن فتاة 👩"]:
        send_delayed(uid, "❌ اختر من الأزرار فقط.", 0.5)
        return
    users[uid]["desired_gender"] = "ذكر" if "رجل" in choice else "أنثى"
    users[uid]["step"] = None
    send_delayed(uid, "🔍 جاري البحث عن شريك...", 0.5)
    threading.Thread(target=find_partner, args=(uid,)).start()

# ===== إدارة الدردشة والمغادرة =====
@bot.message_handler(func=lambda m: m.text in ["❌ مغادرة 🚪", "🚨 إبلاغ"])
def chat_control(message):
    uid = message.chat.id
    text = message.text
    if uid not in active_chats:
        send_delayed(uid, "ℹ️ أنت لست في محادثة حالياً.", 0.5)
        return
    partner = active_chats[uid]
    
    if text == "❌ مغادرة 🚪":
        elapsed = time.time() - leave_timers.get(uid, 0)
        if elapsed < 30:
            remaining = int(30 - elapsed)
            send_delayed(uid, f"⏳ لا يمكنك المغادرة قبل 30 ثانية. انتظر {remaining} ثانية.", 0.5)
            return
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("✅ تأكيد المغادرة"))
        send_delayed(uid, "⚠️ هل تريد فعلاً المغادرة؟", 0.5)
        bot.send_message(uid, "اضغط الزر أدناه للتأكيد:", reply_markup=kb)
    
    elif text == "✅ تأكيد المغادرة":
        bot.send_message(partner, "🚪 غادر شريكك الدردشة.")
        send_delayed(uid, "🚪 غادرت الدردشة.", 0.5)
        for x in (uid, partner):
            active_chats.pop(x, None)
            leave_timers.pop(x, None)
            chat_history.pop(x, None)
    
    elif text == "🚨 إبلاغ":
        history = chat_history.get(uid, [])
        bad_count = sum(1 for msg in history for word in BAD_WORDS if word in msg)
        points = bad_count // 3
        users[partner]["respect"] = max(0, users[partner].get("respect", 80) - points)
        send_delayed(uid, f"✅ تم الإبلاغ عن المستخدم. {points} نقطة/نقاط تم خصمها من الاحترام.", 0.5)

# ===== تحويل الرسائل بين الشريكين مع سجل المحادثة والكشف عن الكلمات البذيئة =====
@bot.message_handler(func=lambda m: True)
def relay(message):
    uid = message.chat.id
    if uid in active_chats:
        partner = active_chats[uid]
        text = message.text
        chat_history.setdefault(uid, []).append(text)
        if len(chat_history[uid]) > 50:
            chat_history[uid].pop(0)
        # كشف الكلمات البذيئة وتطبيق الخصم
        bad_count = sum(1 for word in BAD_WORDS if word in text)
        users[uid]["bad_words_count"] += bad_count
        points = users[uid]["bad_words_count"] // 3 - (users[uid].get("respect_deducted", 0))
        if points > 0:
            users[uid]["respect"] = max(0, users[uid]["respect"] - points)
            users[uid]["respect_deducted"] = users[uid].get("respect_deducted", 0) + points
        sender_name = users.get(uid, {}).get("name") or "مستخدم"
        bot.send_message(partner, f"💬 {sender_name}: {text}")
    else:
        send_delayed(uid, "ℹ️ اختر 🔍 بحث للبدء.", 0.5)

# ===== تشغيل البوت =====
if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
