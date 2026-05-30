import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from data.config import TOKEN
from utils.helper import send_log, build_character_cache

from handlers.inline import router as inline_router
from handlers.main import router as main_router

from utils.commands import set_commands


async def main():
    logging.basicConfig(level=logging.INFO)

    if not TOKEN:
        logging.error("BOT_TOKEN not set")
        return

    api = TelegramAPIServer.from_base(
        "http://telegram-bot-api:8081"
    )

    session = AiohttpSession(api=api)

    bot = Bot(
        token=TOKEN,
        session=session,
        default=DefaultBotProperties()
    )

    try:
        me = await bot.get_me()
        logging.info(
            f"Connected to @{me.username} ({me.id})"
        )
    except Exception:
        logging.exception(
            "Cannot connect to Telegram Bot API"
        )
        return

    dp = Dispatcher()

    dp.include_router(inline_router)
    dp.include_router(main_router)

    build_character_cache()

    try:
        await set_commands(bot)
    except Exception:
        logging.exception(
            "Could not register bot commands"
        )

    logging.info("Bot started")

    try:
        await send_log(
            bot,
            "✅ Bot started successfully"
        )
    except Exception:
        logging.exception(
            "Failed to send log message"
        )

    try:
        await dp.start_polling(
            bot,
            skip_updates=True
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())