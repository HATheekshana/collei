import logging
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram import Router
from utils.helper import normalize_name, find_character_files, find_artifact_files
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME
from utils.artifacts import find_artifact_info

router = Router()

# Base raw URL for files hosted in the GitHub repo
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HATheekshana/collei/main"

@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    query = normalize_name(inline_query.query or "")
    results = []

    bot_username = BOT_USERNAME
    if not bot_username:
        try:
            me = await inline_query.bot.get_me()
            bot_username = me.username
        except Exception:
            bot_username = None

    try:
        def shorten(text: str, max_len: int = 80) -> str:
            t = " ".join(text.split())
            return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"

        for key, display_name in SEARCH_ITEMS.items():
            if query and query not in normalize_name(key):
                continue

            artifact_info = find_artifact_info(key)
            artifact_files = find_artifact_files(key)
            character_files = find_character_files(key)

            if artifact_info:
                summary_parts = []
                for part in ["2-Piece Effect", "4-Piece Effect"]:
                    if part in artifact_info:
                        summary_parts.append(f"{part}: {shorten(artifact_info[part], 70)}")
                summary = " | ".join(summary_parts) or "Artifact info"
                message_text = [display_name, summary]
                if artifact_files:
                    rel = artifact_files[0].replace('\\', '/').lstrip('./')
                    if rel.startswith(('cards/', 'artifacts/', 'guides/')):
                        message_text.append(f"{_GITHUB_RAW_BASE}/{rel}")
                command_text = f"/{key}@{bot_username}" if bot_username else f"/{key}"
                message_text.append(command_text)
                results.append(
                    InlineQueryResultArticle(
                        id=f"artifact-{key}",
                        title=f"{display_name} artifact",
                        description=summary,
                        input_message_content=InputTextMessageContent(
                            message_text="\n\n".join(message_text)
                        )
                    )
                )
            elif character_files:
                rel = character_files[0].replace('\\', '/').lstrip('./')
                preview_url = None
                if rel.startswith(('cards/', 'guides/')):
                    preview_url = f"{_GITHUB_RAW_BASE}/{rel}"

                description = "Character build preview"
                message_text = [display_name]
                if preview_url:
                    description = "Character preview image"
                    message_text.append(preview_url)
                command_text = f"/{key}@{bot_username}" if bot_username else f"/{key}"
                message_text.append(command_text)

                results.append(
                    InlineQueryResultArticle(
                        id=f"char-{key}",
                        title=display_name,
                        description=description,
                        input_message_content=InputTextMessageContent(
                            message_text="\n\n".join(message_text)
                        )
                    )
                )
            else:
                command_text = f"/{key}@{bot_username}" if bot_username else f"/{key}"
                results.append(
                    InlineQueryResultArticle(
                        id=f"empty-{key}",
                        title=display_name,
                        description="No preview available",
                        input_message_content=InputTextMessageContent(
                            message_text=f"{display_name}\n\n{command_text}"
                        )
                    )
                )

            if len(results) >= 50:
                break
    except Exception:
        logging.exception("Inline query failed")
        results = []

    await inline_query.answer(
        results=results,
        cache_time=1,
        is_personal=True
    )
