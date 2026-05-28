from aiogram.types import InlineQuery,InlineQueryResultArticle,InputTextMessageContent,InlineQueryResultPhoto
from aiogram import Router
from utils.helper import normalize_name
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME

_bot_username_cache = None
from utils.helper import find_character_files, find_artifact_files

# Base raw URL for files hosted in the GitHub repo
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HATheekshana/collei/main"

router = Router()
@router.inline_query()
async def inline_search(inline_query: InlineQuery):

    query = normalize_name(
        inline_query.query
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

        # Try to find local files (cards/guides/artifacts) and offer an inline preview
        char_files = find_character_files(key)
        art_files = find_artifact_files(key)

        # Prefer returning a photo result when we have at least one image URL
        first_url = None
        candidates = char_files or art_files
        if candidates:
            # take first file and convert to GitHub raw URL
            rel = candidates[0].replace('\\', '/').lstrip('./')
            # If path already starts with cards/ or artifacts/ or guides/, use directly
            if rel.startswith(('cards/', 'artifacts/', 'guides/')):
                first_url = f"{_GITHUB_RAW_BASE}/{rel}"

        if first_url:
            # Photo result will show preview in the chat even if bot isn't present
            caption_parts = [f"{display_name}"]
            if bot_username:
                caption_parts.append(f"Use /{key}@{bot_username} to fetch full gallery")
            caption = " — ".join(caption_parts)

            results.append(
                InlineQueryResultPhoto(
                    id=f"photo-{key}",
                    photo_url=first_url,
                    thumb_url=first_url,
                    title=display_name,
                    description=f"Preview of {display_name}",
                    input_message_content=InputTextMessageContent(
                        message_text=f"{display_name}\n{first_url}"
                    )
                )
            )
        else:
            # Fallback to an article with plain text (works without bot in chat)
            command_text = f"/{key}@{bot_username}" if bot_username else f"/{key}"
            results.append(
                InlineQueryResultArticle(
                    id=key,
                    title=display_name,
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