import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# Telegram HTTP request logs are useful for errors, but normal request noise
# makes Render logs harder to read.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("hugbot")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit(
        "BOT_TOKEN is not set. Create a bot with @BotFather in Telegram "
        "and add the token as an environment variable."
    )

SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@your_support_username")
PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK_BASE = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
PROFILE_BANNER = ASSETS_DIR / "profile_banner.png"
MENU_BANNER = ASSETS_DIR / "menu_banner.png"

logger.info("BASE_DIR=%s", BASE_DIR)
logger.info("PROFILE_BANNER=%s exists=%s", PROFILE_BANNER, PROFILE_BANNER.exists())
logger.info("MENU_BANNER=%s exists=%s", MENU_BANNER, MENU_BANNER.exists())

# For the demo, data is stored in SQLite.
# On Render Free the local filesystem is ephemeral, so this is fine for a demo,
# but data can be lost after a restart/redeploy. A real production version
# should use a hosted PostgreSQL database.
DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "hugcollect.db")))

BTN_MAIN = "Главная"
BTN_PROFILE = "Личный кабинет"
BTN_MENU = "Меню"
BTN_SUPPORT = "Техническая поддержка"
BTN_BACK = "Вернуться на главную"
BTN_PROMO = "Ввести промокод"
BTN_SUB = "Оформить подписку"
BTN_HUG = "Обнять юзера 🤗"
BTN_SEARCH = "Поиск 👀"
BTN_CHECK = "Проверить получателя"
BTN_HISTORY = "История обнимашек"
BTN_YES = "Да, обнять! 🤗"
BTN_NO = "Нет, отмена"
BTN_HOORAY = "Ура!"

kb_start = ReplyKeyboardMarkup([[BTN_MAIN]], resize_keyboard=True)
kb_home = ReplyKeyboardMarkup(
    [[BTN_PROFILE], [BTN_MENU], [BTN_SUPPORT]], resize_keyboard=True
)
kb_profile = ReplyKeyboardMarkup(
    [[BTN_PROMO], [BTN_SUB], [BTN_BACK]], resize_keyboard=True
)
kb_menu = ReplyKeyboardMarkup(
    [[BTN_HUG], [BTN_SEARCH, BTN_CHECK], [BTN_HISTORY], [BTN_BACK]],
    resize_keyboard=True,
)
kb_support = ReplyKeyboardMarkup([[BTN_BACK]], resize_keyboard=True)
kb_confirm = ReplyKeyboardMarkup([[BTN_YES], [BTN_NO]], resize_keyboard=True)
kb_hooray = ReplyKeyboardMarkup([[BTN_HOORAY]], resize_keyboard=True)

GREETING = "Привет, обнимашка! 🤗\nЧем я могу вам помочь?"
SUPPORT_TEXT = (
    "Если вы столкнулись с проблемой в работе бота — напишите: "
    f"{SUPPORT_USERNAME}\n\n"
    "Это демо-бот виртуальных обнимашек."
)

PROMO_CODES = {"HUG2026": 7}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 3,
                warmth INTEGER NOT NULL DEFAULT 1000,
                sub_active INTEGER NOT NULL DEFAULT 1,
                sub_days_left INTEGER NOT NULL DEFAULT 7,
                ref_code TEXT NOT NULL DEFAULT 'HUGGER',
                checks INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hugs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target TEXT NOT NULL,
                count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def ensure_profile(user_id: int):
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO profiles (user_id) VALUES (?)",
            (user_id,),
        )
        conn.commit()


def get_profile(user_id: int) -> dict:
    ensure_profile(user_id)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        sent = conn.execute(
            "SELECT COUNT(*) FROM hugs WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

    profile = dict(row)
    profile["sub_active"] = bool(profile["sub_active"])
    profile["sent"] = sent
    return profile


def add_promo_days(user_id: int, days: int):
    ensure_profile(user_id)
    with db() as conn:
        conn.execute(
            """
            UPDATE profiles
            SET sub_active = 1,
                sub_days_left = sub_days_left + ?
            WHERE user_id = ?
            """,
            (days, user_id),
        )
        conn.commit()


def add_check(user_id: int):
    ensure_profile(user_id)
    with db() as conn:
        conn.execute(
            "UPDATE profiles SET checks = checks + 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def add_hug(user_id: int, target: str, count: int):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with db() as conn:
        conn.execute(
            "INSERT INTO hugs (user_id, target, count, created_at) VALUES (?, ?, ?, ?)",
            (user_id, target, count, now),
        )
        conn.execute(
            """
            UPDATE profiles
            SET warmth = MIN(1000, warmth + 10)
            WHERE user_id = ?
            """,
            (user_id,),
        )
        conn.commit()


def get_history(user_id: int, limit: int = 10):
    with db() as conn:
        return conn.execute(
            """
            SELECT target, count, created_at
            FROM hugs
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_profile(update.effective_user.id)
    context.user_data["state"] = None
    await update.message.reply_text(
        "Спасибо за подписку! 💎\nБот доступен для работы.",
        reply_markup=kb_start,
    )


async def send_profile(update: Update, profile: dict):
    caption = (
        "👤 Профиль обнимальщика\n\n"
        f"🤗 Уровень — {profile['level']}\n"
        f"💞 Теплота — {profile['warmth']}/1000\n"
        f"💬 Отправлено обнимашек — {profile['sent']}\n"
        f"👀 Проверок совместимости — {profile['checks']}\n"
        f"💛 Подписка — {'Оформлена' if profile['sub_active'] else 'Не оформлена'}\n"
        f"⏳ Осталось дней подписки — {profile['sub_days_left']}\n"
        f"🎁 Реферальный код — {profile['ref_code']}"
    )

    if PROFILE_BANNER.exists():
        try:
            with PROFILE_BANNER.open("rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=kb_profile,
                )
            return
        except Exception:
            logger.exception("Failed to send profile banner: %s", PROFILE_BANNER)

    logger.warning("Profile banner is unavailable: %s", PROFILE_BANNER)
    await update.message.reply_text(caption, reply_markup=kb_profile)


async def send_menu(update: Update):
    if MENU_BANNER.exists():
        try:
            with MENU_BANNER.open("rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption="Выберите действие 👇",
                    reply_markup=kb_menu,
                )
            return
        except Exception:
            logger.exception("Failed to send menu banner: %s", MENU_BANNER)

    logger.warning("Menu banner is unavailable: %s", MENU_BANNER)
    await update.message.reply_text("Выберите действие 👇", reply_markup=kb_menu)


async def run_hug_animation(bot, chat_id: int, message_id: int, user_id: int, target: str):
    """Cosmetic demo animation. No Telegram message is sent to the target."""
    try:
        steps = [10, 25, 40, 60, 80, 100]
        for percent in steps:
            await asyncio.sleep(0.55)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"😴 Идёт процесс отправки обнимашек 😴\n{percent}%",
            )

        hug_count = random.randint(120, 500)
        await asyncio.sleep(0.35)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"🤗 Отправлено объятий — {hug_count} 🤗",
        )

        add_hug(user_id, target, hug_count)
        await bot.send_message(
            chat_id=chat_id,
            text=f"Ура! Обнимашки для {target} готовы 💌",
            reply_markup=kb_hooray,
        )
    except Exception:
        logger.exception(
            "Hug animation failed: chat_id=%s message_id=%s target=%s",
            chat_id, message_id, target,
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    profile = get_profile(user_id)
    state = context.user_data.get("state")

    # Multi-step flows
    if state == "awaiting_hug_target":
        if not text:
            await update.message.reply_text("Введите @username или ID.")
            return

        context.user_data["hug_target"] = text
        context.user_data["state"] = "awaiting_confirm"
        await update.message.reply_text(
            f"Вы уверены, что хотите отправить обнимашки {text}? 🤗",
            reply_markup=kb_confirm,
        )
        return

    if state == "awaiting_confirm":
        if text == BTN_YES:
            context.user_data["state"] = None
            target = context.user_data.get("hug_target", "другу")
            msg = await update.message.reply_text(
                "😴 Идёт процесс отправки обнимашек 😴\n0%",
                reply_markup=ReplyKeyboardRemove(),
            )
            # Run the animation as a background task so the webhook handler
            # returns immediately instead of waiting several seconds.
            context.application.create_task(
                run_hug_animation(
                    context.bot,
                    update.effective_chat.id,
                    msg.message_id,
                    user_id,
                    target,
                ),
                update=update,
            )
        elif text == BTN_NO:
            context.user_data["state"] = None
            await update.message.reply_text(
                "Отменено 🙂", reply_markup=kb_menu
            )
        else:
            await update.message.reply_text(
                "Выберите вариант на клавиатуре 👇",
                reply_markup=kb_confirm,
            )
        return

    if state == "awaiting_promo":
        context.user_data["state"] = None
        code = text.upper()

        if code in PROMO_CODES:
            days = PROMO_CODES[code]
            add_promo_days(user_id, days)
            await update.message.reply_text(
                f"🎉 Промокод принят! +{days} дней подписки.",
                reply_markup=kb_profile,
            )
        else:
            await update.message.reply_text(
                "❌ Такого промокода не существует.",
                reply_markup=kb_profile,
            )
        return

    if state == "awaiting_check_target":
        context.user_data["state"] = None
        add_check(user_id)
        score = random.randint(60, 100)

        await update.message.reply_text(
            f"🤗 Обнимашковость {text}: {score}%\n"
            "(шуточный случайный результат, просто для настроения)",
            reply_markup=kb_menu,
        )
        return

    # Navigation
    if text in (BTN_MAIN, BTN_BACK, BTN_HOORAY):
        context.user_data["state"] = None
        await update.message.reply_text(GREETING, reply_markup=kb_home)

    elif text == BTN_PROFILE:
        await send_profile(update, profile)

    elif text == BTN_MENU:
        await send_menu(update)

    elif text == BTN_SUPPORT:
        await update.message.reply_text(
            SUPPORT_TEXT, reply_markup=kb_support
        )

    elif text == BTN_PROMO:
        context.user_data["state"] = "awaiting_promo"
        await update.message.reply_text(
            "Введите промокод:",
            reply_markup=ReplyKeyboardRemove(),
        )

    elif text == BTN_SUB:
        await update.message.reply_text(
            "Подписка уже активна 💎\n\n"
            "Это демо-версия. Позже сюда можно подключить "
            "Telegram Stars или другую оплату.",
            reply_markup=kb_profile,
        )

    elif text == BTN_HUG:
        context.user_data["state"] = "awaiting_hug_target"
        await update.message.reply_text(
            "Введите @username или ID аккаунта, которому "
            "отправим виртуальные обнимашки 🤗",
            reply_markup=ReplyKeyboardRemove(),
        )

    elif text == BTN_SEARCH:
        await update.message.reply_text(
            "🔍 Раздел «Поиск» пока находится в разработке.",
            reply_markup=kb_menu,
        )

    elif text == BTN_CHECK:
        context.user_data["state"] = "awaiting_check_target"
        await update.message.reply_text(
            "Введите @username для проверки:",
            reply_markup=ReplyKeyboardRemove(),
        )

    elif text == BTN_HISTORY:
        history = get_history(user_id)

        if not history:
            await update.message.reply_text(
                "Пока пусто — вы ещё никого не обнимали 🤗",
                reply_markup=kb_menu,
            )
        else:
            lines = [
                f"• {row['target']} — {row['count']} объятий "
                f"({row['created_at']})"
                for row in history
            ]
            await update.message.reply_text(
                "История обнимашек:\n\n" + "\n".join(lines),
                reply_markup=kb_menu,
            )

    else:
        await update.message.reply_text(
            "Не понимаю 🙈 Воспользуйтесь кнопками ниже.",
            reply_markup=kb_home,
        )


def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    if WEBHOOK_BASE:
        webhook_path = BOT_TOKEN
        webhook_url = f"{WEBHOOK_BASE.rstrip('/')}/{webhook_path}"

        logger.info("Starting webhook mode: %s", webhook_url)

        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        logger.info("No public URL found; starting long polling.")
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
