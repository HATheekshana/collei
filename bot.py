import logging

from telegram.ext import ApplicationBuilder, InlineQueryHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from data.config import TOKEN
from utils.helper import send_log, build_character_cache
from handlers.main import handle_message
from handlers.inline import inline_search, handle_inline_image_callback


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not TOKEN:
        logging.error("BOT_TOKEN not set. Set BOT_TOKEN in environment.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_search))
    app.add_handler(CallbackQueryHandler(handle_inline_image_callback, pattern=r"^img\|"))
    app.add_handler(MessageHandler(filters.COMMAND, handle_message))

    build_character_cache()

    logging.info("Bot started (python-telegram-bot)")

    async def on_startup(application: ContextTypes.DEFAULT_TYPE) -> None:
        await send_log(application.bot, "✅ Bot started successfully")

    app.post_init = on_startup

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()