import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from data.config import TOKEN, SUPPORT_CHAT_ID
from utils.helper import send_log

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
    from utils import storage
    if not await asyncio.to_thread(storage.ready):
        await bot.session.close()
        raise RuntimeError("This database has not been activated. Use the same MONGO_URL and MONGO_TEST_DB as your migrated bot.")
    from handlers.statistics import UsageMiddleware, router as statistics_router
    dp.update.outer_middleware(UsageMiddleware())
    dp.include_router(statistics_router)

    dp.include_router(inline_router)
    from utils.character_details import router as details_router
    dp.include_router(details_router)
    from handlers.update import router as update_router
    dp.include_router(update_router)
    from handlers.artifact_migration import router as artifact_router
    dp.include_router(artifact_router)
    from handlers.weapon_database import router as weapon_router
    dp.include_router(weapon_router)
    dp.include_router(main_router)
    from utils import artifact_db
    await artifact_db.reload()
    from utils import weapon_db
    await weapon_db.reload()

    from utils import character_media_db
    await character_media_db.reload()

    try:
        await set_commands(bot)
    except Exception:
        logging.exception("Could not register bot commands")

    async def _daily_alive_message():
        if not SUPPORT_CHAT_ID:
            logging.info("SUPPORT_CHAT_ID not set; daily alive message disabled")
            return

        while True:
            now = datetime.now(timezone.utc)
            target = now.replace(hour=5, minute=30, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logging.info(f"Daily alive message scheduled in {wait_seconds:.0f} seconds")
            await asyncio.sleep(wait_seconds)

            try:
                await bot.send_message(
                    chat_id=SUPPORT_CHAT_ID,
                    text="🤖 Bot is live! Use /bsync to refresh banner data.",
                )
                logging.info("Sent daily alive message to support group")
            except Exception:
                logging.exception("Failed to send daily alive message")

            # Sleep for one full 24-hour period after sending.
            await asyncio.sleep(24 * 3600)

    asyncio.create_task(_daily_alive_message())

    logging.info("Bot started")

    try:
        await send_log(bot, "✅ Bot started successfully")
    except Exception:
        logging.exception("Failed to send log message")

    try:
        # Polling cannot receive updates while a webhook is registered.
        # Preserve queued updates when switching back to polling.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())