import logging
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram import Router
from utils.helper import normalize_name, find_character_files, find_artifact_files
from data.search_items import SEARCH_ITEMS
from utils.artifacts import find_artifact_info

router = Router()

# Base raw URL for files hosted in the GitHub repo
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HATheekshana/collei/main"

@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    query = normalize_name(inline_query.query or "")
    results = []

    try:
        def shorten(text: str, max_len: int = 80) -> str:
            t = " ".join(text.split())
            return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"

        def hidden_url(url: str) -> str:
            return f'<a href="{url}">&#8203;</a>'

        def url_is_image(path: str) -> bool:
            return path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))

        for key, display_name in SEARCH_ITEMS.items():
            if query and query not in normalize_name(key):
                continue

            artifact_info = find_artifact_info(key)
            artifact_files = find_artifact_files(key)
            character_files = find_character_files(key)

            if artifact_info:
                message_text = [display_name]
                preview_added = False
                for path in artifact_files:
                    if url_is_image(path):
                        rel = path.replace('\\', '/').lstrip('./')
                        message_text.append(f"Preview:{hidden_url(f'{_GITHUB_RAW_BASE}/{rel}')}")
                        preview_added = True
                        break

                for part in ["2-Piece Effect", "4-Piece Effect"]:
                    if part in artifact_info:
                        message_text.append(f"{part}:\n{artifact_info[part]}")

                if not preview_added and artifact_files:
                    rel = artifact_files[0].replace('\\', '/').lstrip('./')
                    message_text.append(f"Preview:{hidden_url(f'{_GITHUB_RAW_BASE}/{rel}')}")

                results.append(
                    InlineQueryResultArticle(
                        id=f"artifact-{key}",
                        title=f"{display_name} artifact",
                        description="Artifact effects preview",
                        input_message_content=InputTextMessageContent(
                            message_text="\n\n".join(message_text),
                            parse_mode="HTML"
                        )
                    )
                )
            elif character_files:
                cards = []
                builds = []
                for path in character_files:
                    rel = path.replace('\\', '/').lstrip('./')
                    url = f"{_GITHUB_RAW_BASE}/{rel}"
                    if rel.startswith('cards/') and url_is_image(rel):
                        cards.append(url)
                    elif rel.startswith('guides/') and url_is_image(rel):
                        builds.append(url)

                message_text = [display_name]
                if cards:
                    for idx, url in enumerate(cards, start=1):
                        message_text.append(f"Card {idx}:{hidden_url(url)}")
                if builds:
                    for idx, url in enumerate(builds, start=1):
                        message_text.append(f"Build {idx}:{hidden_url(url)}")

                if not cards and not builds:
                    message_text.append("No preview available")

                results.append(
                    InlineQueryResultArticle(
                        id=f"char-{key}",
                        title=display_name,
                        description="Character cards and guides",
                        input_message_content=InputTextMessageContent(
                            message_text="\n\n".join(message_text),
                            parse_mode="HTML"
                        )
                    )
                )
            else:
                results.append(
                    InlineQueryResultArticle(
                        id=f"empty-{key}",
                        title=display_name,
                        description="No preview available",
                        input_message_content=InputTextMessageContent(
                            message_text=display_name
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
