import telebot
from config import TOKEN, LEAVE_DELAY
from profile import create_profile, set_interest, users
from matchmaking import search_for_partner
from moderation import check_message, report_user
from messages import WELCOME_TEXT, LEAVE_CONFIRM, delayed_send

bot = telebot.TeleBot(TOKEN)

# بدء التشغيل
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.send_message(message.chat.id, WELCOME_TEXT)
    # هنا تضع خطوات إدخال الاسم والعمر والجنس الخ...

# إرسال رسالة بين شريكين
@bot.message_handler(func=lambda m: True)
def relay_messages(message):
    uid = message.from_user.id
    if uid in users and users[uid].get("chat_partner"):
        partner = users[uid]["chat_partner"]

        if check_message(uid, message.text):
            bot.send_message(uid, "⚠️ تم خصم نقاط الاحترام بسبب كلمة غير لائقة.")

        else:
            bot.send_message(partner, message.text)

# تشغيل
bot.polling()
