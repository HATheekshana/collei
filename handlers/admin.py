from aiogram import types
from utils.artifacts import parse_artifact_payload, save_artifact_info_entry
from data.config import ADMIN_IDS
def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)

async def handle_add_artifact_command(message: types.Message):
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    if not message.text:
        await message.reply("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    artifact_name, artifact_data = parse_artifact_payload(parts[1].strip())
    if not artifact_name:
        await message.reply(
            "Could not parse artifact name. Use /addarti Artifact Name 2-Piece: ... 4-Piece: ..."
        )
        return

    entry = {"name": artifact_name}
    entry.update(artifact_data)
    if not save_artifact_info_entry(entry):
        await message.reply("Failed to save artifact info. Check bot logs.")
        return

    saved_fields = ", ".join(artifact_data.keys()) or "details"
    await message.reply(f"Artifact info saved for {artifact_name} ({saved_fields}).")