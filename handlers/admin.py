import os
from telegram import Message
from utils.artifacts import parse_artifact_payload, save_artifact_info_entry
from data.config import ADMIN_IDS
from data.search_items import SEARCH_ITEMS
from data.config import ARTIFACTS_FOLDER

ALLCOMMANDS_FILE = os.path.join(ARTIFACTS_FOLDER, "allcommands.txt")

def is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


async def handle_add_artifact_command(message: Message):
    if not is_admin(message):
        await message.reply_text("You are not authorized to use this command.")
        return

    if not message.text:
        await message.reply_text("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    artifact_name, artifact_data = parse_artifact_payload(parts[1].strip())
    if not artifact_name:
        await message.reply_text(
            "Could not parse artifact name. Use /addarti Artifact Name 2-Piece: ... 4-Piece: ..."
        )
        return

    entry = {"name": artifact_name}
    entry.update(artifact_data)
    if not save_artifact_info_entry(entry):
        await message.reply_text("Failed to save artifact info. Check bot logs.")
        return

    saved_fields = ", ".join(artifact_data.keys()) or "details"
    await message.reply_text(f"Artifact info saved for {artifact_name} ({saved_fields}).")


async def handle_update_allcommands_command(message: Message):
    """Admin command: regenerate the allcommands list file from SEARCH_ITEMS."""
    if not is_admin(message):
        await message.reply_text("You are not authorized to use this command.")
        return

    if not os.path.isdir(ARTIFACTS_FOLDER):
        os.makedirs(ARTIFACTS_FOLDER, exist_ok=True)

    lines = []
    for key, display in sorted(SEARCH_ITEMS.items(), key=lambda t: t[0]):
        lines.append(f"/{key} - {display}")

    try:
        with open(ALLCOMMANDS_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        await message.reply_text(f"All commands list updated ({len(lines)} entries).")
    except Exception:
        await message.reply_text("Failed to write allcommands file. Check bot logs.")