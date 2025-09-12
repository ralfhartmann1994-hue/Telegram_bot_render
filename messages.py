# messages.py
import random
import time
from stickers import STICKERS

# Messages constants (عربي)
WELCOME = "🎉 مرحبًا بك! استخدم الأزرار للبدء."
HELP = (
    "🆘 <b>مساعدة</b>\n"
    "• 👤 ملفي — عرض بياناتك.\n"
    "• ✏️ تعديل الاسم / 🎂 تعديل العمر.\n"
    "• 🔍 البحث عن دردشة — تختار موضوعًا + جنس الطرف الآخر ثم نبحث لمدة 30 دقيقة.\n"
    "• أثناء الدردشة: 🚨 إبلاغ، 🚪 مغادرة (بعد 30 ثانية) مع تأكيد.\n"
)

WELCOME_MESSAGE = "👋 أهلاً بك في البوت!"
ASK_NAME = "ما اسمك؟"
ASK_GENDER = "اختر جنسك:"
ASK_AGE = "كم عمرك؟"

PROFILE_SAVED = """✅ تم حفظ ملفك:
الاسم: {name}
الجنس: {gender}
العمر: {age}"""

SEARCHING = "⏳ جاري البحث عن شريك مناسب… ابقَ هنا أو عد للقائمة، سنخبرك إن وجدنا شريكًا."
NO_MATCH = "❌ لم نجد شريكًا خلال المدة المحددة. جرّب مرة أخرى لاحقًا — سنسعى لمطابقتك."
INTRO_PARTNER = (
    "✅ <b>تم العثور على شريك للدردشة!</b>\n"
    "✨ تذكير: لا تُظهر أي معلومات حساسة، واحترم الطرف الآخر.\n"
    "ابدأ الحديث بلطف 🙂"
)
LEAVE_CONFIRM = "⚠️ هل تريد مغادرة الدردشة؟\nاختر: نعم ✅ / لا ❌"
LEAVE_TOO_SOON = "⏳ يمكنك المغادرة بعد {remain} ثانية."
LEFT_YOU = "🚪 تم إنهاء الدردشة. عدتَ إلى القائمة الرئيسية."
LEFT_PARTNER = "ℹ️ أنهى الطرف الآخر الدردشة. يمكنك بدء محادثة جديدة."

REPORT_CONFIRM = "🚨 هل تريد إرسال بلاغ لمراجعة آخر الرسائل؟ نعم ✅ / لا ❌"
REPORT_OK = "✅ تم استلام البلاغ وسنراجعه."
REPORT_RESULT = "🔎 نتيجة المراجعة:\n{lines} رسالة\n• كلمات مسيئة: {badwords}\n• نقاط مخصومة: {penalty}\n\nالاحترام الآن: {new_respect}."
MUTED = "⏳ أنت تحت حظر مؤقت حتى انتهاء المدة (~{left} ثانية)."
BANNED = "🚫 حسابك محظور بسبب مخالفات متكررة."

# start messages pools
START_MESSAGES = [
    "😂 أهلاً أهلاً… حضّر نفسك، يمكن تضحك أو يمكن تندم على دخولك!",
    "😏 هلا بك! هذا البوت مثل حلبة مصارعة… بس بالسوالف والنكت.",
    "🙃 دخلت عالم السؤال… كل شيء ممكن يحدث، حتى ضحك على غرائب نفسك!",
    "🔥 هلا! لا تشيل هم، كل اللي راح يسوي لك البوت هو إنه يوصلك لشخص غريب يناقشك في مواضيعك.",
    "😂 حبيبي، انتبه: بعض الناس هون ممكن ينكتوا على طول… وبعضهم على حسابك!",
    "لقد وصلت الى طريق مسدود.. بس منفتحو كرمالك 😎",
    "تفضل يا مولاي...",
    "اي تفضل تفضل تفضل ❤️❤️"
]

FOOTBALL_MESSAGES = [
    "⚽ دخلت عالم الكرة… هل أنت مع برشلونة؟ أو هل فريقك سيخسر أمام ريال مدريد مرة أخرى 😅",
    "🏆 ليفربول يا غالي! حضر شايك، المباراة الكلامية بدأت 😉",
]

POLITICS_MESSAGES = [
    "🌍 اهلاً في ساحة السياسة… هل الحكومات تخبرنا كل الحقيقة؟",
]

RELIGION_MESSAGES = [
    "🕌 أهلاً بك… هنا نناقش الدين والأفكار بحكمة، مع احترام الجميع.",
]

PHILOSOPHY_MESSAGES = [
    "🤔 ما معنى أن تكون موجودًا؟ هل الوجود مجرد صدفة أم اختيار؟",
]

SOCIAL_MESSAGES = [
    "💬 مرحبًا بك… البشر خلقوا للتعارف، لنحترم بعضنا ونتعلم من بعضنا.",
]

def get_welcome_message(topic=None):
    if topic == "START":
        return random.choice(START_MESSAGES)
    if not topic:
        return random.choice(START_MESSAGES)
    t = topic.lower()
    if "رياض" in t or "⚽" in topic:
        return random.choice(FOOTBALL_MESSAGES)
    if "سياس" in t:
        return random.choice(POLITICS_MESSAGES)
    if "دين" in t:
        return random.choice(RELIGION_MESSAGES)
    if "فلسف" in t or "فلسفة" in t:
        return random.choice(PHILOSOPHY_MESSAGES)
    if "تعارف" in t or "سوش" in t:
        return random.choice(SOCIAL_MESSAGES)
    return random.choice(START_MESSAGES)

# webhook-safe send (no sleep)
def delayed_send(bot, chat_id, text, **kwargs):
    # remove delay if provided mistakenly
    kwargs.pop("delay", None)
    try:
        bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        print(f"[delayed_send ERROR] {e} | chat_id={chat_id} | text_preview={str(text)[:120]}")
