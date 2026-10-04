import logging
import re
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
from utils.cards import find_cards_for_character
from utils.guides import find_guides_for_character
from data.search_items import SEARCH_ITEMS
from utils.artifacts import find_artifact_info
from utils.bosses import find_boss
from utils.weapons import find_weapon, build_weapon_html_caption, build_weapon_classic_keyboard, DEFAULT_REFINEMENT, REFINEMENTS
from utils.banner import get_banner_text, get_banner_countdown_text
from utils.endgame import get_endgame_text, get_single_endgame_text, ensure_schedule
from utils.special_media import get_media, get_image_urls, LABELS as SPECIAL_LABELS

router = Router()

# Base raw URL for files hosted in the GitHub repo
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HATheekshana/collei/main"


def _hidden_url(url: str) -> str:
    return f'<a href="{url}">&#8203;</a>'


def _name_words(name: str) -> list:
    """Split a name into lowercase words on spaces/hyphens/underscores, e.g.
    'Scarlet Proof' -> ['scarlet', 'proof']. Used so inline search can match
    any individual word in a multi-word name, not just the whole thing."""
    return [w for w in re.split(r"[\s\-_]+", (name or "").lower()) if w]


def _matches_query(key: str, display_name: str, query: str) -> bool:
    """True if `query` (already normalized: lowercase, no spaces/hyphens/
    underscores) is a prefix of the full key/display name, OR a prefix of
    any individual word within them. This lets 'scarlet' AND 'proof' both
    find 'Scarlet Proof', and narrows the list letter by letter as more of
    the word is typed."""
    if not query:
        return True

    normalized_key = normalize_name(key)
    normalized_display = normalize_name(display_name)
    if normalized_key.startswith(query) or normalized_display.startswith(query):
        return True

    for word in _name_words(key) + _name_words(display_name):
        if word.startswith(query):
            return True

    return False

@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    raw_query = (inline_query.query or "").strip()
    lower_query = raw_query.lower()

    # "@bot abyss" / "@bot theatre" / "@bot stygian" (defaults to the CURRENT
    # phase set), or "@bot next abyss" / "@bot current stygian" etc. for a
    # specific phase. Shows the countdown as text, with a hidden preview link
    # + Previous/Next cycling buttons for the stored images — same pattern as
    # the character card/artifact previews below.
    _CATEGORY_ALIASES = {"abyss": "abyss", "theatre": "theatre", "theater": "theatre", "stygian": "stygian"}

    def _parse_special_query(q: str):
        phase = "current"
        rest = q
        if rest.startswith("next "):
            phase, rest = "next", rest[5:].strip()
        elif rest.startswith("current "):
            phase, rest = "current", rest[8:].strip()
        elif rest == "next" or rest == "current":
            return None, None  # handled by the next/current block below
        category = _CATEGORY_ALIASES.get(rest)
        return (phase, category) if category else (None, None)

    special_phase, special_category = _parse_special_query(lower_query)
    if special_category:
        label = SPECIAL_LABELS.get(special_category, special_category.title())
        phase_label = "Next" if special_phase == "next" else "Current"

        try:
            if special_category == "stygian":
                await ensure_schedule()
            countdown_text = get_single_endgame_text(special_category, mode=special_phase)
        except Exception:
            logging.exception("Inline %s %s countdown failed", special_phase, special_category)
            countdown_text = f"🎭 <b>{label}</b>\n<code>Couldn't fetch the countdown right now.</code>"

        image_urls = get_image_urls(special_phase, special_category)

        message_lines = [f"<b>{phase_label} {label}</b>", "", countdown_text]
        reply_kb = None
        if image_urls:
            message_lines.append(f"Preview:{_hidden_url(image_urls[0])}")
            reply_kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="Previous",
                        callback_data=f"simg|{special_phase}|{special_category}|{max(0, 0 - 1)}",
                    ),
                    InlineKeyboardButton(text=f"1/{len(image_urls)}", callback_data=f"simg|{special_phase}|{special_category}|0"),
                    InlineKeyboardButton(
                        text="Next",
                        callback_data=f"simg|{special_phase}|{special_category}|{1 if len(image_urls) > 1 else 0}",
                    ),
                ]]
            )
        else:
            message_lines.append("No preview images added yet.")

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=f"special-{special_phase}-{special_category}",
                    title=f"{phase_label} {label}",
                    description="Countdown + record image preview",
                    input_message_content=InputTextMessageContent(
                        message_text="\n".join(message_lines),
                        parse_mode="HTML",
                    ),
                    reply_markup=reply_kb,
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    # "@bot next" / "@bot current" / "@bot next hutao" — works in any chat,
    # even ones the bot isn't a member of, since inline results are sent by
    # the user, not the bot.
    if lower_query == "next" or lower_query == "current" or lower_query.startswith("next ") or lower_query.startswith("current "):
        mode = "next" if lower_query.startswith("next") else "current"
        rest = raw_query[len(mode):].strip()
        await ensure_schedule()
        try:
            if rest:
                text = get_banner_countdown_text(rest, mode=mode) + "\n\n" + get_endgame_text(mode=mode)
            else:
                text = get_banner_text(mode=mode) + "\n\n" + get_endgame_text(mode=mode)
        except Exception:
            logging.exception("Inline %s countdown failed", mode)
            text = "Couldn't build the countdown right now, try again in a bit."

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=f"{mode}-countdown",
                    title=f"{mode.title()} banner & endgame countdown",
                    description="Tap to send here",
                    input_message_content=InputTextMessageContent(
                        message_text=text,
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    query = normalize_name(raw_query)
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

        from utils.search import search_catalog
        for token, display_name in search_catalog().items():
            kind, key = token.split(":", 1)
            normalized_key = normalize_name(key)
            normalized_display = normalize_name(display_name)
            # match prefix so 'r' finds 'razor'; also matches any individual
            # word so 'proof' finds 'Scarlet Proof', not just 'scarlet'.
            if not _matches_query(key, display_name, query):
                continue

            artifact_info = find_artifact_info(key) if kind == "a" else None
            artifact_files = find_artifact_files(key)
            character_files = find_character_files(key)

            # --- Boss inline result ---
            boss = find_boss(display_name) if kind == "b" else None
            if boss and boss.get("file_id"):
                from aiogram.types import InlineQueryResultPhoto
                results.append(
                    InlineQueryResultPhoto(
                        id=f"boss-{key}",
                        photo_url=f"https://api.telegram.org/file/bot{{token}}/placeholder",  # unused, file_id used via cached_photo
                        thumbnail_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/No_image_available.svg/240px-No_image_available.svg.png",
                        title=display_name,
                        description="Boss",
                        caption=f"<b>Boss:</b> {boss['name']}",
                        parse_mode="HTML",
                        # Use CachedPhoto to send by file_id
                    )
                )
                # Replace with cached photo result
                results.pop()
                from aiogram.types import InlineQueryResultCachedPhoto
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=f"boss-{key}",
                        photo_file_id=boss["file_id"],
                        title=display_name,
                        description="Boss",
                        caption=f"<b>Boss:</b> {boss['name']}",
                        parse_mode="HTML",
                    )
                )
                if len(results) >= 50:
                    break
                continue

            # --- Weapon inline result ---
            weapon_entry = find_weapon(key) if kind == "w" else None
            if weapon_entry:
                weapon_caption = build_weapon_html_caption(weapon_entry, DEFAULT_REFINEMENT)
                weapon_kb = build_weapon_classic_keyboard(
                    weapon_entry, inline_query.from_user.id, DEFAULT_REFINEMENT
                )
                results.append(
                    InlineQueryResultArticle(
                        id=f"weapon-{key}",
                        title=display_name,
                        description="Weapon stats & passive",
                        thumbnail_url=weapon_entry.get("image_url"),
                        input_message_content=InputTextMessageContent(
                            message_text=weapon_caption,
                            parse_mode="HTML",
                        ),
                        reply_markup=weapon_kb,
                    )
                )
                if len(results) >= 50:
                    break
                continue

            # collect image URLs from imgBB (preferred) or fallback to local files
            def collect_images_with_source() -> tuple[list, list, list]:
                """Return (all_imgs, cards, builds)"""
                all_imgs = []
                cards = []
                builds = []

                # Get cards and guides from JSON with imgbb URLs
                cards_entries = find_cards_for_character(key) if kind == "c" else []
                guides_entries = find_guides_for_character(key) if kind == "c" else []

                for entry in cards_entries:
                    if entry.get("image_url"):
                        url = entry["image_url"]
                        all_imgs.append(url)
                        cards.append(url)

                for entry in guides_entries:
                    if entry.get("image_url"):
                        url = entry["image_url"]
                        all_imgs.append(url)
                        builds.append(url)

                # Artifact image uploaded via /addarti (imgbb URL) takes
                # priority over local files below.
                if artifact_info and artifact_info.get("image_url"):
                    all_imgs[0:0] = artifact_info.get("image_urls") or [artifact_info["image_url"]]

                # Fallback to local files if no imgbb URLs (for backward compat)
                for p in artifact_files:
                    if url_is_image(p):
                        relp = p.replace('\\', '/').lstrip('./')
                        url = make_url(relp)
                        all_imgs.append(url)

                for p in character_files:
                    relp = p.replace('\\', '/').lstrip('./')
                    if relp.startswith('cards/') and url_is_image(relp):
                        url = make_url(relp)
                        all_imgs.append(url)
                        cards.append(url)
                    elif relp.startswith('guides/') and url_is_image(relp):
                        url = make_url(relp)
                        all_imgs.append(url)
                        builds.append(url)

                return all_imgs, cards, builds

            images, cards_urls, builds_urls = collect_images_with_source()

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
            elif images or character_files:
                # Character has cards/guides (either from imgbb or local files)
                preview_url = cards_urls[0] if cards_urls else (builds_urls[0] if builds_urls else (images[0] if images else None))

                message_text = [display_name]
                if preview_url:
                    message_text.append(f"Preview:{hidden_url(preview_url)}")
                else:
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

                from utils.character_details import remember_inline, inline_keyboard
                token = remember_inline(key, "\n\n".join(message_text),
                                        inline_query.from_user.id, images, display_name)
                if token:
                    reply = InlineKeyboardMarkup(**inline_keyboard(token, images))
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


@router.callback_query(lambda c: c.data and c.data.startswith("wpni|"))
async def handle_weapon_inline_refinement_callback(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split("|", 3)
    if len(parts) != 4:
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        return

    if callback.from_user.id != user_id:
        try:
            await callback.answer("This button is not for you.", show_alert=True)
        except Exception:
            pass
        return

    key, refinement = parts[2], parts[3]
    if refinement not in REFINEMENTS:
        refinement = DEFAULT_REFINEMENT

    weapon_entry = find_weapon(key)
    if not weapon_entry:
        return

    text = build_weapon_html_caption(weapon_entry, refinement)
    kb = build_weapon_classic_keyboard(weapon_entry, user_id, refinement)

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
        logging.exception("Failed to edit weapon inline preview message")


@router.callback_query(lambda c: c.data and c.data.startswith("simg|"))
async def handle_special_inline_image_callback(callback: CallbackQuery):
    try:
        await callback.answer()

        parts = callback.data.split("|")
        if len(parts) != 4:
            return

        _, phase, category, idx_str = parts
        try:
            idx = int(idx_str)
        except Exception:
            idx = 0

        image_urls = get_image_urls(phase, category)
        if not image_urls:
            await callback.answer("No images available", show_alert=False)
            return

        idx = max(0, min(idx, len(image_urls) - 1))
        url = image_urls[idx]

        label = SPECIAL_LABELS.get(category, category.title())
        phase_label = "Next" if phase == "next" else "Current"

        try:
            if category == "stygian":
                await ensure_schedule()
            countdown_text = get_single_endgame_text(category, mode=phase)
        except Exception:
            logging.exception("Inline %s %s countdown refresh failed", phase, category)
            countdown_text = f"🎭 <b>{label}</b>"

        message_lines = [
            f"<b>{phase_label} {label}</b>",
            "",
            countdown_text,
            f"Preview:{_hidden_url(url)}",
        ]

        total = len(image_urls)
        prev_idx = idx - 1 if idx > 0 else total - 1
        next_idx = idx + 1 if idx < total - 1 else 0

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⬅️", callback_data=f"simg|{phase}|{category}|{prev_idx}"),
                    InlineKeyboardButton(text=f"{idx+1}/{total}", callback_data=f"simg|{phase}|{category}|{idx}"),
                    InlineKeyboardButton(text="➡️", callback_data=f"simg|{phase}|{category}|{next_idx}"),
                ]
            ]
        )

        text = "\n".join(message_lines)

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
            logging.exception("Failed to edit special media inline preview message")

    except Exception:
        logging.exception("Special media inline image callback failed")


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

        artifact_info = None  # This callback cycles character images only.
        artifact_files = find_artifact_files(key)
        character_files = find_character_files(key)

        def collect_images_with_source() -> list[str]:
            image_urls = list((artifact_info or {}).get("image_urls") or ([(artifact_info or {})["image_url"]] if (artifact_info or {}).get("image_url") else []))
            cards_entries = find_cards_for_character(key)
            guides_entries = find_guides_for_character(key)

            for entry in cards_entries:
                if entry.get("image_url"):
                    image_urls.append(entry["image_url"])
            for entry in guides_entries:
                if entry.get("image_url"):
                    image_urls.append(entry["image_url"])

            for p in artifact_files:
                if url_is_image(p):
                    rel = p.replace('\\', '/').lstrip('./')
                    image_urls.append(make_url(rel))
            for p in character_files:
                rel = p.replace('\\', '/').lstrip('./')
                if rel.startswith('cards/') and url_is_image(rel):
                    image_urls.append(make_url(rel))
                if rel.startswith('guides/') and url_is_image(rel):
                    image_urls.append(make_url(rel))
            return image_urls

        images = collect_images_with_source()

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