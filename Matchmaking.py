import time
from config import SEARCH_TIMEOUT
from messages import delayed_send, SEARCHING_TEXT, NO_MATCH_TEXT
from profile import users

waiting = []  # قائمة انتظار للمطابقة

def search_for_partner(bot, user_id, interest, gender_preference):
    start_time = time.time()
    delayed_send(bot, user_id, SEARCHING_TEXT, delay=1)

    # حفظ اهتمام المستخدم
    users[user_id]["interest"] = interest

    while time.time() - start_time < SEARCH_TIMEOUT:
        for other in waiting:
            if other != user_id and users[other]["interest"] == interest:
                # مطابقة ناجحة
                users[user_id]["chat_partner"] = other
                users[other]["chat_partner"] = user_id
                waiting.remove(other)
                return other
        time.sleep(2)

    # لم يتم العثور على شريك
    delayed_send(bot, user_id, NO_MATCH_TEXT, delay=1)
    return None
