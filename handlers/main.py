import logging
import os
from aiogram import Router, types
from utils.helper import send_log
from handlers.admin import handle_add_artifact_command
from utils.artifacts import find_artifact_info
from utils.helper import find_character_files, find_artifact_files
from handlers.media import send_artifact_preview, send_cached_media_group
from data.aliases import ALIASES
from data.search_items import SEARCH_ITEMS
router = Router()
@router.message()
async def handle_message(message: types.Message):
    # Handle commands
    if message.text and message.text.startswith("/"):
        command = message.text.split()[0][1:].split('@')[0].lower()
        user = message.from_user

        # Special commands that are always allowed
        SPECIAL_COMMANDS = {"start", "addarti", "allcommands"}
        
        # If the command is not in SEARCH_ITEMS and not a special command and not an alias, ignore it silently
        if command not in SEARCH_ITEMS and command not in SPECIAL_COMMANDS and command not in ALIASES:
            return

        username = (
            f"@{user.username}"
            if user.username else
            "None"
        )

        await send_log(
            message.bot,
            f"📥 Command Used\n\n"
            f"👤 User: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📛 Username: {username}\n"
            f"💬 Command: /{command}"
        )
        if command == "start":
            await message.reply(
                "Welcome! Send a character command like /ganyu or /raiden to get their guides and material cards."
            )
            return

        if command == "addarti":
            await handle_add_artifact_command(message)
            return
        if command == "allcommands":
            # Show a generated list of available commands to the user.
            try:
                from data.search_items import SEARCH_ITEMS

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
                # Prefer sending remote previews from the GitHub artifacts folder
                # This uses a hidden zero-width-space link so Telegram shows the image preview
                for idx, path in enumerate(artifact_files):
                    try:
                        fname = os.path.basename(path)
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                            # fallback to sending the local file if it's not an image
                            if os.path.isfile(path):
                                await message.reply_document(types.FSInputFile(path))
                            continue

                        cap = artifact_caption if idx == 0 else None
                        await send_artifact_preview(message, fname, caption=cap)
                    except Exception:
                        logging.exception("Failed to send preview %s", path)

                artifact_caption = None

            if artifact_caption:
                await message.reply(artifact_caption, parse_mode="HTML")
            return

        character = ALIASES.get(command, command)
        files = find_character_files(character)

        if not files:
            await message.reply(f"No files found for {character.title()}.")
            return

        
        # Telegram allows max 10 media per album
        CHUNK_SIZE = 10

        for i in range(0, len(files), CHUNK_SIZE):

            chunk = files[i:i + CHUNK_SIZE]

            await send_cached_media_group(
                message,
                chunk
            )