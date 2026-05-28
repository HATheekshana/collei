from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultPhoto
from aiogram import Router
from utils.helper import normalize_name, find_character_files, find_artifact_files
from data.search_items import SEARCH_ITEMS
from utils.artifacts import find_artifact_info

router = Router()

# Base raw URL for files hosted in the GitHub repo
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HATheekshana/collei/main"

@router.inline_query()
async def inline_search(inline_query: InlineQuery):

    query = normalize_name(
        inline_query.query or ""
    )

    results = []

    for key, display_name in SEARCH_ITEMS.items():
        if query and query not in normalize_name(key):
            continue

        artifact_info = find_artifact_info(key)
        artifact_files = find_artifact_files(key)
        character_files = find_character_files(key)

        if artifact_info:
            lines = [f"{artifact_info.get('name', display_name)}"]
            for part in ["2-Piece Effect", "4-Piece Effect"]:
                if part in artifact_info:
                    lines.append(f"{part}: {artifact_info[part]}")
            if artifact_files:
                rel = artifact_files[0].replace('\\', '/').lstrip('./')
                if rel.startswith(('cards/', 'artifacts/', 'guides/')):
                    url = f"{_GITHUB_RAW_BASE}/{rel}"
                    lines.append(url)
            results.append(
                InlineQueryResultArticle(
                    id=f"artifact-{key}",
                    title=f"{display_name} artifact info",
                    description="Artifact details and image link",
                    input_message_content=InputTextMessageContent(
                        message_text="\n\n".join(lines)
                    )
                )
            )
        elif character_files:
            rel = character_files[0].replace('\\', '/').lstrip('./')
            preview_url = None
            if rel.startswith(('cards/', 'guides/')):
                preview_url = f"{_GITHUB_RAW_BASE}/{rel}"

            if preview_url:
                results.append(
                    InlineQueryResultPhoto(
                        id=f"char-{key}",
                        photo_url=preview_url,
                        thumb_url=preview_url,
                        title=display_name,
                        description="Character build preview",
                        input_message_content=InputTextMessageContent(
                            message_text=f"{display_name}\n{preview_url}"
                        )
                    )
                )
            else:
                results.append(
                    InlineQueryResultArticle(
                        id=f"char-{key}",
                        title=display_name,
                        description="Character build preview",
                        input_message_content=InputTextMessageContent(
                            message_text=display_name
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

    await inline_query.answer(
        results=results,
        cache_time=1,
        is_personal=True
    )