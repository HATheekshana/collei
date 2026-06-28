import logging
import os
from aiogram import Router, types
from utils.helper import send_log
from handlers.admin import handle_add_artifact_command
from utils.artifacts import find_artifact_info
from utils.helper import find_character_files, find_artifact_files
from handlers.media import send_rich_slideshow
from utils.search import find_search_matches, render_search_keyboard, send_search_result
from data.aliases import ALIASES
from data.search_items import SEARCH_ITEMS
from data.config import BOT_USERNAME
router = Router()
@router.message()
async def handle_message(message: types.Message):
    logging.info(f"Message received: {message.text}")
    # Handle commands
    if message.text and message.text.startswith("/"):
        command = message.text.split()[0][1:].split('@')[0].lower()
        logging.info(f"Command extracted: {command}")
        user = message.from_user

        # Special commands that are always allowed
        SPECIAL_COMMANDS = {"start", "search", "addarti", "allcommands"}
        
        # If the command is not in SEARCH_ITEMS and not a special command and not an alias, ignore it silently
        should_ignore = command not in SEARCH_ITEMS and command not in SPECIAL_COMMANDS and command not in ALIASES
        logging.info(f"Command '{command}' - should_ignore={should_ignore}")
        
        if should_ignore:
            logging.info(f"Ignoring command: {command}")
            return

        try:
            username = (
                f"@{user.username}"
                if user.username else
                "None"
            )

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
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(
                                text="Add me to your group",
                                url=group_link,
                            )
                        ]
                    ]
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
        if command == "allcommands":
            # Show a generated list of available commands to the user.
            try:
                lines = [f"/{k} - {v}" for k, v in sorted(SEARCH_ITEMS.items(), key=lambda t: t[0])]
                text = "Available commands:\n" + "\n".join(lines)

                # Telegram limits message size; split if necessary
                MAX = 4000
                for i in range(0, len(text), MAX):
                    await message.reply(text[i:i+MAX])
            except Exception:
                logging.exception("Failed to build allcommands list")
                await message.reply("Failed to retrieve commands list.")

            return

        if command == "search":
            query = message.text.partition(" ")[2].strip()
            if not query:
                await message.reply("Usage: /search [name]\nExample: /search collei")
                return

            matches = find_search_matches(query)
            if not matches:
                await message.reply(
                    "No search results found. Try another keyword or /allcommands."
                )
                return

            if len(matches) == 1:
                await send_search_result(message, matches[0])
                return

            keyboard = render_search_keyboard(matches, message.from_user.id)
            await message.reply(
                f"Search results for \"{query}\":",
                reply_markup=keyboard,
            )
            return

        artifact_info = find_artifact_info(command)
        artifact_files = find_artifact_files(command)

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

        character = ALIASES.get(command, command)
        files = find_character_files(character)

        if not files:
            await message.reply(f"No files found for {character.title()}.")
            return

        # Send rich slideshow with character files.
        CHUNK_SIZE = 50
        caption = (
                "Artifacts moved to inline mode.\n"
                "Use @collei_help_bot + name to search."
            )
        for i in range(0, len(files), CHUNK_SIZE):
            chunk = files[i:i + CHUNK_SIZE]
            chunk_caption = caption if i == 0 else None

            try:
                await send_rich_slideshow(
                    message,
                    chunk,
                    caption=chunk_caption,
                )
            except Exception:
                logging.exception("Rich slideshow failed")


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
