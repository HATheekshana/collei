import asyncio
import logging

from aiogram import Bot, Dispatcher

from data.config import TOKEN
from utils.helper import send_log, build_character_cache

from handlers.inline import router as inline_router
from handlers.main import router as main_router


async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=TOKEN)

    dp = Dispatcher()

    dp.include_router(inline_router)
    dp.include_router(main_router)

    build_character_cache()

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