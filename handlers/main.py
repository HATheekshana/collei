import logging
import os
from telegram import InputFile, Update
from telegram.ext import ContextTypes
from utils.helper import send_log, find_character_files, find_artifact_files
from handlers.admin import handle_add_artifact_command
from utils.artifacts import find_artifact_info
from data.aliases import ALIASES
from data.config import IGNORED_COMMANDS
from handlers.media import send_artifact_preview, send_cached_media_group


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text or not message.text.startswith("/"):
        return

    command = message.text.split()[0][1:].split("@")[0].lower()
    user = message.from_user

    if command in IGNORED_COMMANDS:
        return

    username = (
        f"@{user.username}"
        if user and user.username else
        "None"
    )

    await send_log(
        message.bot,
        f"📥 Command Used\n\n"
        f"👤 User: {user.full_name if user else 'Unknown'}\n"
        f"🆔 ID: {user.id if user else 'Unknown'}\n"
        f"📛 Username: {username}\n"
        f"💬 Command: /{command}"
    )

    if command == "start":
        await message.reply_text(
            "Welcome! Send a character command like /ganyu or /raiden to get their guides and material cards."
        )
        return

    if command == "addarti":
        await handle_add_artifact_command(message)
        return

    if command == "allcommands":
        try:
            from data.search_items import SEARCH_ITEMS

            lines = [f"/{k} - {v}" for k, v in sorted(SEARCH_ITEMS.items(), key=lambda t: t[0])]
            text = "Available commands:\n" + "\n".join(lines)

            MAX = 4000
            for i in range(0, len(text), MAX):
                await message.reply_text(text[i:i+MAX])
        except Exception:
            logging.exception("Failed to build allcommands list")
            await message.reply_text("Failed to retrieve commands list.")

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
                    fname = os.path.basename(path)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        if os.path.isfile(path):
                            await message.reply_document(InputFile(path))
                        continue

                    cap = artifact_caption if idx == 0 else None
                    await send_artifact_preview(message, fname, caption=cap)
                except Exception:
                    logging.exception("Failed to send preview %s", path)

            artifact_caption = None

        if artifact_caption:
            await message.reply_text(artifact_caption, parse_mode="HTML")
        return

    character = ALIASES.get(command, command)
    files = find_character_files(character)

    if not files:
        await message.reply_text(f"No files found for {character.title()}.")
        return

    CHUNK_SIZE = 10
    for i in range(0, len(files), CHUNK_SIZE):
        chunk = files[i:i + CHUNK_SIZE]
        await send_cached_media_group(message, chunk)
