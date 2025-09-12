# config.py
import os

# وقت البحث بالثواني (30 دقيقة)
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", 30 * 60))
# فاصل تحقق الـ watcher بالثواني
SEARCH_CHECK_INTERVAL = int(os.getenv("SEARCH_CHECK_INTERVAL", 10))

RESPECT_PENALTY_PER_BADWORD = int(os.getenv("RESPECT_PENALTY_PER_BADWORD", 5))
PARTIAL_BAN_THRESHOLD = int(os.getenv("PARTIAL_BAN_THRESHOLD", 40))
FULL_BAN_THRESHOLD = int(os.getenv("FULL_BAN_THRESHOLD", 25))
PARTIAL_BAN_DAYS = int(os.getenv("PARTIAL_BAN_DAYS", 7))
MAX_HISTORY_TO_REVIEW = int(os.getenv("MAX_HISTORY_TO_REVIEW", 50))

USERS_DB_PATH = os.getenv("USERS_DB_PATH", "users_db.json")

# موضوعات افتراضية (يمكن تعديلها)
TOPICS = ["عام", "رياضة", "سياسة", "دين", "فلسفة", "تعارف"]
GENDERS = ["ذكر", "أنثى"]
TARGET_GENDERS = ["👨 رجل", "👩 امرأة"]

# Leave delay (seconds) before user can leave chat
LEAVE_DELAY = int(os.getenv("LEAVE_DELAY", 30))

# Webhook settings (اختياري)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", None)
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "webhook")
PORT = int(os.getenv("PORT", "5000"))
