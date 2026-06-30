import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from data.config import TOKEN
from utils.helper import send_log, build_character_cache, sync_media_to_telegram

from handlers.inline import router as inline_router
from handlers.main import router as main_router

from utils.commands import set_commands


async def main():
    logging.basicConfig(level=logging.INFO)

    if not TOKEN:
        logging.error("BOT_TOKEN not set")
        return

    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties()
    )

    try:
        me = await bot.get_me()
        logging.info(f"Connected to @{me.username} ({me.id})")
    except Exception:
        logging.exception("Cannot connect to Telegram Bot API")
        return

    dp = Dispatcher()

    dp.include_router(inline_router)
    dp.include_router(main_router)

    build_character_cache()

    try:
        await set_commands(bot)
    except Exception:
        logging.exception("Could not register bot commands")

    # Upload any local cards/guides that don't have a Telegram file_id yet,
    # then delete the local copies to free VPS space.
    try:
        await sync_media_to_telegram(bot)
    except Exception:
        logging.exception("Media sync failed")

    logging.info("Bot started")

    try:
        await send_log(bot, "✅ Bot started successfully")
    except Exception:
        logging.exception("Failed to send log message")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())