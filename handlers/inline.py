from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram import Router
from utils.helper import normalize_name
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME

_bot_username_cache = None
router = Router()

@router.inline_query()
async def inline_search(inline_query: InlineQuery):

    query = normalize_name(
        inline_query.query or ""
    )

    results = []

    # Determine bot username once (from config or by querying the bot)
    bot_username = BOT_USERNAME
    if not bot_username:
        global _bot_username_cache
        if _bot_username_cache is None:
            try:
                me = await inline_query.bot.get_me()
                _bot_username_cache = me.username
            except Exception:
                _bot_username_cache = None
        bot_username = _bot_username_cache

    for key, display_name in SEARCH_ITEMS.items():
        if query and query not in normalize_name(key):
            continue

        command_text = f"/{key}@{bot_username}" if bot_username else f"/{key}"
        title = f"{display_name} (@{bot_username})" if bot_username else display_name
        results.append(
            InlineQueryResultArticle(
                id=command_text,
                title=title,
                description=f"Send {display_name}",
                input_message_content=InputTextMessageContent(
                    message_text=command_text
                )
            )
        )

        if len(results) >= 50:
            break

    await inline_query.answer(
        results=results,
        cache_time=1,
        is_personal=True
    )