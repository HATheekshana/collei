"""Artifact DB maintenance commands. Migration is no longer registered."""
import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from data.config import ADMIN_IDS
from utils import artifact_db

router = Router()
_lock = asyncio.Lock()

@router.message(Command("artifactcheck", "artifactreload"))
async def check_artifacts(message: types.Message):
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        await message.reply("Only bot admins can use this command.")
        return
    if _lock.locked():
        await message.reply("Artifact reload is already running.")
        return
    async with _lock:
        status = await message.reply("Reading artifacts from MongoDB…")
        try:
            count = await artifact_db.reload()
            from utils.artifacts import load_artifact_info
            missing = sum(not entry.get("image_url") for entry in load_artifact_info().values())
            await status.edit_text(f"Artifact source: MongoDB\nLoaded: {count}\nWithout public image URL: {missing}\nNo artifact JSON or local images are used.")
        except Exception as error:
            await status.edit_text(f"Artifact database unavailable: {type(error).__name__}", parse_mode=None)
