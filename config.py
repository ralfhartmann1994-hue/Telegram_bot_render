# config.py
import os

# ===== التوكن وإعدادات الإدارة =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")  # خزّنه في Render → Environment
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري لإرسال بلاغات

# ===== التسجيل/المطابقة =====
SEARCH_TIMEOUT = 30 * 60       # نصف ساعة (بالثواني)
LEAVE_DELAY = 30               # لا يمكن المغادرة قبل 30 ثانية من بداية المحادثة

# ===== الاحترام والعقوبات =====
RESPECT_START = 80
PENALTY_PER_HIT = 5            # خصم 5 لكل ضربة (حسب المراحل)
WARN_THRESHOLD = 40            # عند/أقل من 40 = حظر جزئي
BAN_THRESHOLD = 25             # عند/أقل من 25 = حظر كامل
PARTIAL_BAN_DAYS = 7           # مدة الحظر الجزئي بالأيام

# ===== مواضيع النقاش =====
TOPICS = ["🎭 فلسفة", "🕌 دين", "🏛️ سياسة", "🤝 تعارف", "⚽ رياضة"]
GENDERS = ["ذكر", "أنثى"]
TARGET_GENDERS = ["👨 رجل", "👩 امرأة"]

# ===== Webhook =====
WEBHOOK_PATH = "bot_webhook"  # الجزء الأخير من رابط Webhook
