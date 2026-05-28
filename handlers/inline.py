from aiogram.types import InlineQuery,InlineQueryResultArticle,InputTextMessageContent
from aiogram import Router
from utils.helper import normalize_name
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME

_bot_username_cache = None

router = Router()
@router.inline_query()
async def inline_search(inline_query: InlineQuery):

    query = normalize_name(
        inline_query.query
    )

    results = []

    for key, display_name in SEARCH_ITEMS.items():

        if query and query not in normalize_name(key):
            continue

        results.append(
            InlineQueryResultArticle(
                id=key,
                title=display_name,
                description=f"Send {display_name}",
                input_message_content=InputTextMessageContent(
                    message_text=f"/{key}"
                )
            )
        )

        # If we have a bot username, offer a variant with the username appended
        try:
            bot_username = BOT_USERNAME
            if not bot_username:
                # try cached lookup from inline_query.bot
                global _bot_username_cache
                if _bot_username_cache is None:
                    try:
                        me = await inline_query.bot.get_me()
                        _bot_username_cache = me.username
                    except Exception:
                        _bot_username_cache = None
                bot_username = _bot_username_cache

            if bot_username:
                results.append(
                    InlineQueryResultArticle(
                        id=f"{key}@{bot_username}",
                        title=f"{display_name} (@{bot_username})",
                        description=f"Send {display_name} to a group (with bot mention)",
                        input_message_content=InputTextMessageContent(
                            message_text=f"/{key}@{bot_username}"
                        )
                    )
                )
        except Exception:
            # don't break inline on username lookup failures
            pass

        if len(results) >= 50:
            break

    await inline_query.answer(
        results=results,
        cache_time=1,
        is_personal=True
    )