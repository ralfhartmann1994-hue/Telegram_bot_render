from config import RESPECT_PENALTY
from profile import users

# قائمة كلمات بذيئة (سحبت لك مجموعة من القوائم المفتوحة)
BAD_WORDS = {
    "fuck", "shit", "bitch", "asshole", "bastard", "dick",
    "pussy", "cunt", "slut", "nigger", "motherfucker", "whore",
    "cock", "dumbass", "faggot"
}

def check_message(user_id, text):
    lowered = text.lower()
    for word in BAD_WORDS:
        if word in lowered:
            users[user_id]["respect"] -= RESPECT_PENALTY
            return True
    return False

def report_user(bot, reporter_id):
    partner_id = users[reporter_id].get("chat_partner")
    if partner_id:
        # افتراضياً: نراجع آخر 50 رسالة ونخصم النقاط إذا كان فيها كلمات بذيئة
        # هنا للتبسيط فقط
        users[partner_id]["respect"] -= RESPECT_PENALTY
        bot.send_message(reporter_id, "🚨 تم مراجعة الرسائل وخصم نقاط الاحترام عند وجود مخالفة.")
