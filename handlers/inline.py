import logging
from urllib.parse import quote
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
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
    logging.info("Inline query received: %s", inline_query.query)

    try:
        def shorten(text: str, max_len: int = 80) -> str:
            t = " ".join(text.split())
            return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"

        def hidden_url(url: str) -> str:
            return f'<a href="{url}">&#8203;</a>'

        def url_is_image(path: str) -> bool:
            return path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))

        def make_url(rel: str) -> str:
            return f"{_GITHUB_RAW_BASE}/{quote(rel, safe='/:')}" if rel else ""

        for key, display_name in SEARCH_ITEMS.items():
            normalized_key = normalize_name(key)
            normalized_display = normalize_name(display_name)
            # match prefix so 'r' finds 'razor', etc.
            if query and not (
                normalized_key.startswith(query) or normalized_display.startswith(query)
            ):
                continue

            artifact_info = find_artifact_info(key)
            artifact_files = find_artifact_files(key)
            character_files = find_character_files(key)

            # collect image URLs for this entry
            def collect_images() -> list:
                imgs = []
                for p in artifact_files:
                    if url_is_image(p):
                        relp = p.replace('\\', '/').lstrip('./')
                        imgs.append(make_url(relp))
                for p in character_files:
                    relp = p.replace('\\', '/').lstrip('./')
                    if relp.startswith('cards/') and url_is_image(relp):
                        imgs.append(make_url(relp))
                    if relp.startswith('guides/') and url_is_image(relp):
                        imgs.append(make_url(relp))
                return imgs

            images = collect_images()

            if artifact_info:
                message_text = [display_name]
                preview_url = images[0] if images else None

                if preview_url:
                    message_text.append(f"Preview:{hidden_url(preview_url)}")

                for part in ["2-Piece Effect", "4-Piece Effect"]:
                    if part in artifact_info:
                        message_text.append(f"{part}:\n{artifact_info[part]}")

                results.append(
                    InlineQueryResultArticle(
                        id=f"artifact-{key}",
                        title=f"{display_name} artifact",
                        description="Artifact effects preview",
                        thumbnail_url=preview_url,
                        input_message_content=InputTextMessageContent(
                            message_text="\n\n".join(message_text),
                            parse_mode="HTML"
                        ),
                    )
                )
            elif character_files:
                cards = []
                builds = []
                preview_url = None

                for path in character_files:
                    rel = path.replace('\\', '/').lstrip('./')
                    url = make_url(rel)
                    if rel.startswith('cards/') and url_is_image(rel):
                        cards.append(url)
                        if not preview_url:
                            preview_url = url
                    elif rel.startswith('guides/') and url_is_image(rel):
                        builds.append(url)
                        if not preview_url:
                            preview_url = url

                message_text = [display_name]
                if preview_url:
                    message_text.append(f"{hidden_url(preview_url)}")

                if cards:
                    for idx, url in enumerate(cards, start=1):
                        message_text.append(f"{hidden_url(url)}")
                if builds:
                    for idx, url in enumerate(builds, start=1):
                        message_text.append(f"{hidden_url(url)}")

                if not cards and not builds:
                    message_text.append("No preview available")

                # build keyboard to cycle character previews
                reply = None
                if images:
                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(text="Previous", callback_data=f"img|{key}|{max(0, 0-1)}"),
                                InlineKeyboardButton(text=f"1/{len(images)}", callback_data=f"img|{key}|0"),
                                InlineKeyboardButton(text="Next", callback_data=f"img|{key}|{1 if len(images)>1 else 0}"),
                            ]
                        ]
                    )
                    reply = kb

                results.append(
                    InlineQueryResultArticle(
                        id=f"char-{key}",
                        title=display_name,
                        description="Character cards and guides",
                        thumbnail_url=preview_url,
                        input_message_content=InputTextMessageContent(
                            message_text="\n\n".join(message_text),
                            parse_mode="HTML"
                        ),
                        reply_markup=reply if reply is not None else None,
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

    # If no results found, include a fallback article and a switch-to-PM button
    if not results:
        fallback = InlineQueryResultArticle(
            id="no-results",
            title="No results — open bot",
            description="Open the bot to search or try a different query",
            input_message_content=InputTextMessageContent(
                message_text="No inline previews available. Open the bot to enable full search."
            )
        )
        results = [fallback]

    logging.info("Inline results count: %d", len(results))

    await inline_query.answer(
        results=results,
        cache_time=1,
        is_personal=True,
        switch_pm_text="Open bot for more",
        switch_pm_parameter="inline"
    )


@router.callback_query(lambda c: c.data and c.data.startswith("img|"))
async def handle_inline_image_callback(callback: CallbackQuery):
    try:
        await callback.answer()

        parts = callback.data.split("|")
        if len(parts) != 3:
            return

        key = parts[1]
        try:
            idx = int(parts[2])
        except Exception:
            idx = 0

        def url_is_image(path: str) -> bool:
            return path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))

        def hidden_url(url: str) -> str:
            return f'<a href="{url}">&#8203;</a>'

        def make_url(rel: str) -> str:
            return f"{_GITHUB_RAW_BASE}/{quote(rel, safe='/:')}" if rel else ""

        artifact_info = find_artifact_info(key)
        artifact_files = find_artifact_files(key)
        character_files = find_character_files(key)

        images = []
        for p in artifact_files:
            if url_is_image(p):
                rel = p.replace('\\', '/').lstrip('./')
                images.append(make_url(rel))
        for p in character_files:
            rel = p.replace('\\', '/').lstrip('./')
            if rel.startswith('cards/') and url_is_image(rel):
                images.append(make_url(rel))
            if rel.startswith('guides/') and url_is_image(rel):
                images.append(make_url(rel))

        if not images:
            await callback.answer("No images available", show_alert=False)
            return

        # clamp/normalize index
        idx = max(0, min(idx, len(images) - 1))
        url = images[idx]

        display_name = SEARCH_ITEMS.get(key, key.title())

        message_lines = [display_name, f"Preview:{hidden_url(url)}"]

        if artifact_info:
            for part in ["2-Piece Effect", "4-Piece Effect"]:
                if part in artifact_info:
                    message_lines.append(f"{part}:\n{artifact_info[part]}")
        else:
            # list small cards/builds summary with index
            for i, img in enumerate(images, start=1):
                message_lines.append(f"Image {i}:{hidden_url(img)}")

        # build keyboard
        total = len(images)
        prev_idx = idx - 1 if idx > 0 else total - 1
        next_idx = idx + 1 if idx < total - 1 else 0

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⬅️", callback_data=f"img|{key}|{prev_idx}"),
                    InlineKeyboardButton(text=f"{idx+1}/{total}", callback_data=f"img|{key}|{idx}"),
                    InlineKeyboardButton(text="➡️", callback_data=f"img|{key}|{next_idx}"),
                ]
            ]
        )

        text = "\n\n".join(message_lines)

        # edit the inline message
        try:
            if callback.inline_message_id:
                await callback.bot.edit_message_text(
                    text=text,
                    inline_message_id=callback.inline_message_id,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            elif callback.message:
                await callback.bot.edit_message_text(
                    text=text,
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
        except Exception:
            logging.exception("Failed to edit inline preview message")

    except Exception:
        logging.exception("Inline image callback failed")
