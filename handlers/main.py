import asyncio
import logging
import os
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command
from utils.helper import send_log, resolve_character_media
from handlers.admin import handle_add_artifact_command
from handlers.boss_admin import handle_bossimg_command
from handlers.card_guide_admin import handle_addcard_command, handle_addguide_command, handle_delcard_command, handle_delguide_command
from utils.bosses import find_boss
from utils.artifacts import find_artifact_info
from utils.helper import find_artifact_files
from handlers.media import send_cached_media_group, send_media_slideshow
from utils.search import find_search_matches, render_search_keyboard, send_search_result
from utils.banner import get_banner_countdown_text, fetch_banner_data_from_hoyolab, get_banner_icons, get_banner_text, update_banner_data
from data.aliases import ALIASES
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME, ADMIN_IDS

router = Router()


async def _send_character_results(message: types.Message, character: str):
    """Resolve media (imgBB URL preferred, Telegram file_id fallback) and send as rich slideshow."""
    logging.info(f"_send_character_results called with character: {character}")
    media_items = await resolve_character_media(message.bot, character)

    logging.info(f"Got {len(media_items)} media items: {media_items[:2] if media_items else 'None'}")
    if not media_items:
        await message.reply(f"No files found for {character.title()}.")
        return

    await send_media_slideshow(message, media_items, caption=character.title())


async def _reply_or_answer(message: types.Message, text: str):
    """message.reply() fails with 'message to be replied not found' if the
    original command message has already vanished (deleted, expired, etc.)
    by the time we respond. Fall back to a plain send in that case."""
    try:
        await message.reply(text, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message to be replied not found" in str(e):
            await message.answer(text, parse_mode="HTML")
        else:
            raise


async def _call_with_flood_retry(action, max_retries: int = 1):
    """Run an aiogram send call, retrying (once, by default) if Telegram's
    flood control (TelegramRetryAfter / 429) kicks in on busy chats."""
    for attempt in range(max_retries + 1):
        try:
            return await action()
        except TelegramRetryAfter as e:
            if attempt >= max_retries:
                raise
            wait_for = getattr(e, "retry_after", 5) + 1
            logging.warning(f"Flood control hit, waiting {wait_for}s before retry")
            await asyncio.sleep(wait_for)


async def _send_banner_rich(message: types.Message, text: str, icons: list[str]):
    """
    Send banner info as native Telegram photo(s) with an HTML caption.
    (send_media_slideshow's <figcaption> path HTML-escapes the caption, which
    would turn our <b>/<code> tags into literal text, so we build a plain
    Telegram media group here instead — that's what actually renders bold text
    and images together.)
    """
    # Telegram allows up to 10 items in a media group, but capping lower
    # keeps requests small and far less likely to trip flood control in busy chats.
    icons = [url for url in icons if url][:6]
    if not icons:
        await _reply_or_answer(message, text)
        return

    if len(icons) == 1:
        try:
            await _call_with_flood_retry(
                lambda: message.reply_photo(icons[0], caption=text, parse_mode="HTML")
            )
            return
        except TelegramBadRequest as e:
            if "message to be replied not found" in str(e):
                try:
                    await _call_with_flood_retry(
                        lambda: message.answer_photo(icons[0], caption=text, parse_mode="HTML")
                    )
                    return
                except Exception:
                    logging.exception("Failed to send single banner photo without reply ref")
            else:
                logging.exception("Failed to send single banner photo")
        except Exception:
            logging.exception("Failed to send single banner photo")
        await _reply_or_answer(message, text)
        return

    media = [
        types.InputMediaPhoto(media=url, caption=text, parse_mode="HTML") if idx == 0
        else types.InputMediaPhoto(media=url)
        for idx, url in enumerate(icons)
    ]
    try:
        await _call_with_flood_retry(
            lambda: message.answer_media_group(
                media,
                reply_parameters=types.ReplyParameters(message_id=message.message_id),
            )
        )
        return
    except TelegramBadRequest as e:
        if "message to be replied not found" in str(e):
            try:
                await _call_with_flood_retry(lambda: message.answer_media_group(media))
                return
            except Exception:
                logging.exception("Failed to send banner media group without reply ref")
        else:
            logging.exception("Failed to send banner media group")
    except Exception:
        logging.exception("Failed to send banner media group")
    await _reply_or_answer(message, text)


@router.message()
async def handle_message(message: types.Message):
    if not message.text or not message.text.startswith("/"):
        return

    command = message.text.split()[0][1:].split('@')[0].lower()
    if not command:
        return

    logging.info(f"Command received: {command}")
    user = message.from_user

    SPECIAL_COMMANDS = {"start", "search", "allcommands"}
    ADMIN_COMMANDS = {"addarti", "next", "current", "bupdate", "bossimg", "addcard", "addguide", "delcard", "delguide", "bsync"}

    should_ignore = command not in SEARCH_ITEMS and command not in SPECIAL_COMMANDS and command not in ADMIN_COMMANDS and command not in ALIASES
    logging.info(f"Command '{command}' - should_ignore={should_ignore}")

    if should_ignore:
        logging.info(f"Ignoring command: {command}")
        return

    try:
        username = f"@{user.username}" if user.username else "None"
        await send_log(
            message.bot,
            f"Command Used\n\n"
            f"User: {user.full_name}\n"
            f"ID: {user.id}\n"
            f"Username: {username}\n"
            f"Command: /{command}"
        )
    except Exception as e:
        logging.exception("Error in send_log: %s", e)

    if command == "start":
        bot_username = BOT_USERNAME
        if bot_username:
            bot_username = bot_username.lstrip("@")
        if not bot_username:
            try:
                me = await message.bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = None

        group_link = None
        if bot_username:
            group_link = f"https://t.me/{bot_username}?startgroup=true"

        button = None
        if group_link:
            button = types.InlineKeyboardMarkup(
                inline_keyboard=[[
                    types.InlineKeyboardButton(text="Add me to your group", url=group_link)
                ]]
            )

        inline_hint = ""
        if bot_username:
            inline_hint = f"\n\nYou can also search inline in any chat by typing @{bot_username} and your query."

        await message.reply(
            "Welcome to Collei Bot!\n\n"
            "Send a character command like /ganyu or /collei to get guides and cards.\n"
            "Use /allcommands to see every available search command." + inline_hint,
            reply_markup=button,
        )
        return

    if command == "addarti":
        await handle_add_artifact_command(message)
        return

    if command == "bossimg":
        await handle_bossimg_command(message)
        return

    if command == "addcard":
        await handle_addcard_command(message)
        return

    if command == "addguide":
        await handle_addguide_command(message)
        return

    if command == "delcard":
        await handle_delcard_command(message)
        return

    if command == "delguide":
        await handle_delguide_command(message)
        return

    if command == "allcommands":
        try:
            lines = [f"/{k} - {v}" for k, v in sorted(SEARCH_ITEMS.items(), key=lambda t: t[0])]
            text = "Available commands:\n" + "\n".join(lines)
            MAX = 4000
            for i in range(0, len(text), MAX):
                await message.reply(text[i:i + MAX])
        except Exception:
            logging.exception("Failed to build allcommands list")
            await message.reply("Failed to retrieve commands list.")
        return

    if command == "next":
        query = message.text.partition(" ")[2].strip()
        if query:
            await message.reply(get_banner_countdown_text(query, mode="next"), parse_mode="HTML")
        else:
            text = get_banner_text(mode="next")
            await _send_banner_rich(message, text, get_banner_icons("next"))
        return

    if command == "current":
        query = message.text.partition(" ")[2].strip()
        if query:
            await message.reply(get_banner_countdown_text(query, mode="current"), parse_mode="HTML")
        else:
            text = get_banner_text(mode="current")
            await _send_banner_rich(message, text, get_banner_icons("current"))
        return

    if command == "bupdate":
        parts = message.text.split(maxsplit=3)
        if len(parts) != 3:
            await message.reply("Usage: /bupdate [nextchar1] [nextchar2]")
            return
        if not message.from_user or message.from_user.id not in ADMIN_IDS:
            await message.reply("You are not authorized to use this command.")
            return
        next_characters = [parts[1], parts[2]]
        update_banner_data(next_characters=next_characters)
        await message.reply("Next banner characters updated.", parse_mode="HTML")
        return

    if command == "bsync":
        if not message.from_user or message.from_user.id not in ADMIN_IDS:
            await _reply_or_answer(message, "You are not authorized to use this command.")
            return
        
        await _reply_or_answer(message, "🔄 Syncing banner data from the Genshin calendar...")
        result = await fetch_banner_data_from_hoyolab()

        if result:
            current_chars = result.get("current_characters", [])
            next_chars = result.get("next_characters", [])
            current_icons = result.get("current_icons", [])
            next_icons = result.get("next_icons", [])

            text = (
                "✅ <b>Banner data synced successfully!</b>\n\n"
                f"<b>Current:</b> {', '.join(current_chars) if current_chars else '—'}\n"
                f"<b>Next:</b> {', '.join(next_chars) if next_chars else '—'}"
            )
            await _send_banner_rich(message, text, current_icons + next_icons)
        else:
            await _reply_or_answer(
                message,
                "❌ Failed to sync banner data.\n\n"
                "<b>Troubleshooting:</b>\n"
                "1. Make sure the bot's host can reach <code>api.ennead.cc</code> (check network/egress settings)\n"
                "2. The calendar API may be temporarily down — check the bot logs for details\n"
                "3. Use /bsync again after resolving the issue.",
            )
        return

    if command == "search":
        query = message.text.partition(" ")[2].strip()
        if not query:
            await message.reply("Usage: /search [name]\nExample: /search collei")
            return

        matches = find_search_matches(query)
        if not matches:
            await message.reply("No search results found. Try another keyword or /allcommands.")
            return

        if len(matches) == 1:
            await send_search_result(message, matches[0])
            return

        keyboard = render_search_keyboard(matches, message.from_user.id)
        await message.reply(f'Search results for "{query}":', reply_markup=keyboard)
        return

    # --- Artifact check ---
    artifact_info = find_artifact_info(command)
    artifact_files = find_artifact_files(command)

    # --- Boss check ---
    boss_display = SEARCH_ITEMS.get(command)
    boss = find_boss(boss_display) if boss_display else None
    if boss and boss.get("file_id"):
        try:
            await message.reply_photo(
                photo=boss["file_id"],
                caption=f"<b>Boss:</b> {boss['name']}",
                parse_mode="HTML",
            )
        except Exception:
            logging.exception("Failed to send boss photo")
        return

    if artifact_info or artifact_files:
        artifact_caption = None
        if artifact_info:
            info_lines = [f"<b>Artifact:</b> {artifact_info.get('name', command.title())}\n\n"]
            for key in ["2-Piece Effect", "4-Piece Effect"]:
                if key in artifact_info:
                    info_lines.append(f"<b>{key}</b>\n{artifact_info[key]}")
            artifact_caption = "\n\n".join(info_lines)

        if artifact_files:
            for idx, path in enumerate(artifact_files):
                try:
                    if idx == 0:
                        await message.reply_photo(
                            types.FSInputFile(path),
                            caption=artifact_caption,
                            parse_mode="HTML"
                        )
                    else:
                        await message.reply_photo(types.FSInputFile(path))
                except Exception:
                    logging.exception("Failed to send artifact photo %s", path)
        elif artifact_caption:
            await message.reply(artifact_caption, parse_mode="HTML")
        return

    # --- Character cards + guides ---
    character = ALIASES.get(command, command)
    await _send_character_results(message, character)


@router.callback_query(lambda c: c.data and c.data.startswith("search|"))
async def handle_search_button(callback: types.CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split("|", 2)
    if len(parts) != 3:
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

    key = parts[2]
    if not callback.message:
        return

    await send_search_result(callback.message, key)

    try:
        await callback.message.delete()
    except Exception:
        pass