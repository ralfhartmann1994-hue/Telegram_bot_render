# main.py
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message

from config import TOKEN, ADMIN_CHAT_ID, TOPICS, GENDERS, TARGET_GENDERS, LEAVE_DELAY
from storage import load_users, save_users, ensure_user, users
from profile import sanitize_name, sanitize_age, profile_text, append_history, end_session, start_history
from moderation import is_muted, apply_respect, review_history_and_penalize
from matchmaking import add_to_wait, try_match, start_timeout_watcher, remove_from_wait
from messages import (WELCOME, HELP, SEARCHING, INTRO_PARTNER, NO_MATCH,
                      LEAVE_CONFIRM, LEAVE_TOO_SOON, LEFT_YOU, LEFT_PARTNER,
                      REPORT_CONFIRM, REPORT_OK, REPORT_RESULT, MUTED, BANNED, delayed_send)

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN مفقود. أضفه في Render → Environment.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ============ القوائم ============
def main_menu(in_chat: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("👤 ملفي"))
    kb.add(KeyboardButton("✏️ تعديل الاسم"), KeyboardButton("🎂 تعديل العمر"))
    kb.add(KeyboardButton("🔍 البحث عن دردشة"))
    if in_chat:
        kb.add(KeyboardButton("🚨 إبلاغ"), KeyboardButton("🚪 مغادرة الدردشة"))
    kb.add(KeyboardButton("🆘 مساعدة"))
    return kb

def topics_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i in range(0, len(TOPICS), 2):
        row = [KeyboardButton(TOPICS[i])]
        if i + 1 < len(TOPICS):
            row.append(KeyboardButton(TOPICS[i+1]))
        kb.add(*row)
    return kb

def target_gender_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("👨 رجل"), KeyboardButton("👩 امرأة"))
    kb.add(KeyboardButton("أي"))
    return kb

def yes_no_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("نعم ✅"), KeyboardButton("لا ❌"))
    return kb

# ============ حالات ============
@bot.message_handler(commands=["start"])
def cmd_start(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        delayed_send(bot, uid, BANNED, delay=0.4)
        return

    if u.get("gender") is None:
        u["state"] = "AWAIT_GENDER"
        save_users()
        delayed_send(bot, uid, WELCOME, delay=0.4, reply_markup=ReplyKeyboardRemove())
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("ذكر"), KeyboardButton("أنثى"), KeyboardButton("أخرى"))
        delayed_send(bot, uid, "اختر الجنس (مرة واحدة فقط):", delay=0.8, reply_markup=kb)
        return

    u["state"] = None
    save_users()
    delayed_send(bot, uid, "مرحبًا من جديد! اختر من القائمة:", delay=0.4, reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["help"])
def cmd_help(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return
    delayed_send(bot, uid, HELP, delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner"))))

@bot.message_handler(commands=["profile"])
def cmd_profile(m: Message):
    uid = m.from_user.id
    ensure_user(uid)
    delayed_send(bot, uid, profile_text(users[uid]), delay=0.2, reply_markup=main_menu(in_chat=bool(users[uid].get("partner"))))

# ============ الإدخال النصي العام ============
@bot.message_handler(func=lambda msg: True, content_types=["text"])
def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    ensure_user(uid)
    u = users[uid]
    if u.get("banned_full"):
        return

    state = u.get("state")

    # —— التسجيل الأول ——
    if state == "AWAIT_GENDER":
        if txt not in GENDERS:
            kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.add(KeyboardButton("ذكر"), KeyboardButton("أنثى"), KeyboardButton("أخرى"))
            delayed_send(bot, uid, "اختر من الأزرار: ذكر / أنثى / أخرى", delay=0.3, reply_markup=kb)
            return
        u["gender"] = txt
        u["state"] = "AWAIT_NAME"
        save_users()
        delayed_send(bot, uid, "أدخل اسمك (٢–٣٠ حرفًا، بدون أرقام):", delay=0.3, reply_markup=ReplyKeyboardRemove())
        return

    if state == "AWAIT_NAME":
        name = sanitize_name(txt)
        if not name:
            delayed_send(bot, uid, "❌ الاسم غير صالح. حاول مجددًا:", delay=0.3)
            return
        u["name"] = name
        u["state"] = "AWAIT_AGE"
        save_users()
        delayed_send(bot, uid, "أدخل عمرك (10–120):", delay=0.3)
        return

    if state == "AWAIT_AGE":
        age = sanitize_age(txt)
        if age is None:
            delayed_send(bot, uid, "❌ العمر غير صالح. أدخل رقمًا بين 10 و120:", delay=0.3)
            return
        u["age"] = age
        u["state"] = None
        save_users()
        delayed_send(bot, uid, "✅ تم الحفظ.\n" + profile_text(u), delay=0.4, reply_markup=main_menu(in_chat=False))
        delayed_send(bot, uid, "اضغط: 🔍 البحث عن دردشة عند جاهزيتك.", delay=0.5)
        return

    # —— أزرار القائمة —— 
    if txt == "👤 ملفي":
        delayed_send(bot, uid, profile_text(u), delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "✏️ تعديل الاسم":
        u["state"] = "EDIT_NAME"
        save_users()
        delayed_send(bot, uid, "أدخل الاسم الجديد:", delay=0.2, reply_markup=ReplyKeyboardRemove())
        return

    if state == "EDIT_NAME":
        name = sanitize_name(txt)
        if not name:
            delayed_send(bot, uid, "❌ الاسم غير صالح. حاول مجددًا:", delay=0.2)
            return
        u["name"] = name
        u["state"] = None
        save_users()
        delayed_send(bot, uid, "✅ تم التحديث.\n" + profile_text(u), delay=0.3, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "🎂 تعديل العمر":
        u["state"] = "EDIT_AGE"
        save_users()
        delayed_send(bot, uid, "أدخل العمر الجديد (10–120):", delay=0.2, reply_markup=ReplyKeyboardRemove())
        return

    if state == "EDIT_AGE":
        age = sanitize_age(txt)
        if age is None:
            delayed_send(bot, uid, "❌ العمر غير صالح. أدخل رقمًا بين 10 و120:", delay=0.2)
            return
        u["age"] = age
        u["state"] = None
        save_users()
        delayed_send(bot, uid, "✅ تم التحديث.\n" + profile_text(u), delay=0.3, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "🆘 مساعدة":
        delayed_send(bot, uid, HELP, delay=0.2, reply_markup=main_menu(in_chat=bool(u.get("partner"))))
        return

    if txt == "🔍 البحث عن دردشة":
        # تحقق اكتمال الملف
        if not (u.get("gender") and u.get("name") and u.get("age")):
            delayed_send(bot, uid, "⚠️ أكمل التسجيل أولًا عبر /start.", delay=0.3)
            return
        u["state"] = "CHOOSE_TOPIC"
        save_users()
        delayed_send(bot, uid, "اختر موضوع النقاش:", delay=0.2, reply_markup=topics_menu())
        return

    if state == "CHOOSE_TOPIC":
        if txt not in TOPICS:
            delayed_send(bot, uid, "❌ اختر من الأزرار:", delay=0.2, reply_markup=topics_menu())
            return
        u["topic"] = txt
        u["state"] = "CHOOSE_TARGET_GENDER"
        save_users()
        delayed_send(bot, uid, "اختر الجنس الذي تود الدردشة معه:", delay=0.2, reply_markup=target_gender_menu())
        return

    if state == "CHOOSE_TARGET_GENDER":
        if txt not in TARGET_GENDERS:
            delayed_send(bot, uid, "❌ اختر من الأزرار:", delay=0.2, reply_markup=target_gender_menu())
            return
        u["search_pref"] = "أي" if txt == "أي" else txt
        u["state"] = None
        save_users()
        # أضِف لقائمة الانتظار وحاول المطابقة فورًا
        add_to_wait(u["topic"], uid, u["search_pref"])
        delayed_send(bot, uid, SEARCHING, delay=0.5, reply_markup=main_menu(in_chat=False))
        # جرّب مطابقة فورية
        partner_id = try_match(uid, u["topic"])
        if partner_id:
            start_chat(uid, partner_id)
        return

    # —— داخل محادثة —— 
    if u.get("partner"):
        # حظر جزئي؟
        muted, left = is_muted(u)
        if muted:
            delayed_send(bot, uid, MUTED.format(left=left), delay=0.2)
            return

        # أزرار الدردشة
        if txt == "🚪 مغادرة الدردشة":
            # لا تُمرر للطرف الآخر — فقط تأكيد عندك
            started = u.get("chat_started_at") or 0
            elapsed = time.time() - started
            if elapsed < LEAVE_DELAY:
                delayed_send(bot, uid, LEAVE_TOO_SOON.format(remain=int(LEAVE_DELAY - elapsed)), delay=0.2)
                return
            u["state"] = "CONFIRM_LEAVE"
            save_users()
            delayed_send(bot, uid, LEAVE_CONFIRM, delay=0.2, reply_markup=yes_no_menu())
            return

        if u.get("state") == "CONFIRM_LEAVE":
            if txt == "نعم ✅":
                # أنهِ الجلسة
                pid = u.get("partner")
                p = users.get(pid)
                end_session(u, p)
                delayed_send(bot, uid, LEFT_YOU, delay=0.2, reply_markup=main_menu(in_chat=False))
                # أبلغ الطرف الآخر فقط بانتهاء الدردشة (بدون تفاصيل أزرار)
                if pid:
                    try:
                        delayed_send(bot, pid, LEFT_PARTNER, delay=0.2, reply_markup=main_menu(in_chat=False))
                    except Exception as e:
                        print(f"[LEAVE NOTIFY PARTNER] {e}")
                u["state"] = None
                save_users()
                return
            elif txt == "لا ❌":
                u["state"] = None
                save_users()
                delayed_send(bot, uid, "تم الإلغاء. تابع الدردشة 👌", delay=0.2)
                return
            else:
                delayed_send(bot, uid, "اختر: نعم ✅ / لا ❌", delay=0.2, reply_markup=yes_no_menu())
                return

        if txt == "🚨 إبلاغ":
            # تأكيد عند المبلّغ فقط
            u["state"] = "CONFIRM_REPORT"
            save_users()
            delayed_send(bot, uid, REPORT_CONFIRM, delay=0.2, reply_markup=yes_no_menu())
            return

        if u.get("state") == "CONFIRM_REPORT":
            if txt == "نعم ✅":
                pid = u.get("partner")
                p = users.get(pid)
                hist = (u.get("history") or [])[-50:]
                you_line, other_line = review_history_and_penalize(uid, pid, hist)
                delayed_send(bot, uid, REPORT_OK, delay=0.2)
                delayed_send(bot, uid, REPORT_RESULT.format(
                    lines=f"• {you_line}\n• {other_line}",
                    respect=users[uid].get("respect", 80)
                ), delay=0.3)
                # إخطار الأدمن (اختياري)
                if ADMIN_CHAT_ID:
                    try:
                        bot.send_message(int(ADMIN_CHAT_ID), f"🚨 بلاغ من {uid} ضد {pid}\n{you_line}\n{other_line}")
                    except Exception as e:
                        print(f"[ADMIN REPORT] {e}")
                u["state"] = None
                save_users()
                return
            elif txt == "لا ❌":
                u["state"] = None
                save_users()
                delayed_send(bot, uid, "تم الإلغاء. تابع الدردشة 👌", delay=0.2)
                return
            else:
                delayed_send(bot, uid, "اختر: نعم ✅ / لا ❌", delay=0.2, reply_markup=yes_no_menu())
                return

        # تطبيق الاحترام على الرسالة (لا تُظهر الاسم — فقط تمرير النص)
        warn = apply_respect(uid, txt)
        if warn:
            delayed_send(bot, uid, warn, delay=0.1)
            # في حال صار حظر كامل، أنهِ الجلسة
            if users[uid].get("banned_full"):
                pid = u.get("partner")
                p = users.get(pid)
                end_session(u, p)
                try:
                    delayed_send(bot, pid, "⚠️ تم إنهاء الدردشة بسبب مخالفة الطرف الآخر.", delay=0.2, reply_markup=main_menu(in_chat=False))
                except Exception as e:
                    print(f"[BAN NOTIFY] {e}")
                return

        # مرّر الرسالة للطرف الآخر فقط كنص
        pid = u.get("partner")
        p = users.get(pid)
        if not p:
            # شريك مفقود — رجوع للقائمة
            end_session(u, None)
            delayed_send(bot, uid, LEFT_PARTNER, delay=0.2, reply_markup=main_menu(in_chat=False))
            return

        append_history(u, p, uid, txt)
        try:
            bot.send_message(pid, txt)
        except Exception as e:
            print(f"[RELAY] {e}")
        return

    # —— خارج محادثة وأوامر غير مفهومة —— 
    delayed_send(bot, uid, "❔ لم أفهم. استخدم الأزرار بالأسفل.", delay=0.2, reply_markup=main_menu(in_chat=False))

# ============ بدء محادثة/إنهاؤها ============
def start_chat(u1_id: int, u2_id: int):
    u1 = users[u1_id]; u2 = users[u2_id]
    u1["partner"] = u2_id
    u2["partner"] = u1_id
    start_history(u1)  # resets history & sets chat_started_at
    start_history(u2)
    # إزالة من الانتظار
    remove_from_wait(u1_id)
    remove_from_wait(u2_id)
    save_users()
    # رسالة تعريف خفيفة (بدون أسماء ضمن الرسائل اللاحقة)
    try:
        delayed_send(bot, u1_id, INTRO_PARTNER, delay=0.5, reply_markup=main_menu(in_chat=True))
        delayed_send(bot, u2_id, INTRO_PARTNER, delay=0.6, reply_markup=main_menu(in_chat=True))
    except Exception as e:
        print(f"[INTRO] {e}")

# ============ التشغيل ============
def main():
    print("[BOOT] Loading users...")
    load_users()
    print(f"[BOOT] Users: {len(users)}")
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"[WEBHOOK] {e}")
    start_timeout_watcher(bot)
    print("[RUN] polling…")
    bot.infinity_polling(skip_pending=True, timeout=20)

if __name__ == "__main__":
    main()
