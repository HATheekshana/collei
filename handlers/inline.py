from aiogram.types import InlineQuery,InlineQueryResultArticle,InputTextMessageContent
from aiogram import Router
from utils.helper import normalize_name
from data.search_items import SEARCH_ITEMS

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

        if len(results) >= 50:
            break

    await inline_query.answer(
        results=results,
        cache_time=1,
        is_personal=True
    )