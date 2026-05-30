import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from data.config import TOKEN
from utils.helper import send_log, build_character_cache

from handlers.inline import router as inline_router
from handlers.main import router as main_router

from utils.commands import set_commands


async def main():
    logging.basicConfig(level=logging.INFO)

    if not TOKEN:
        logging.error("BOT_TOKEN not set. Set BOT_TOKEN in environment.")
        return

    session = AiohttpSession(
        api="http://telegram-bot-api:8081"
    )

    bot = Bot(
        token=TOKEN,
        session=session
    )

    dp = Dispatcher()

    dp.include_router(inline_router)
    dp.include_router(main_router)

    build_character_cache()
    await set_commands(bot)
    logging.info("Bot started (aiogram v3)")

    await send_log(
        bot,
        "✅ Bot started successfully"
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