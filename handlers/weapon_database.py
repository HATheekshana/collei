"""Admin refresh of the MongoDB weapon cache."""
import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from data.config import ADMIN_IDS
from handlers.update import _lock
from utils import weapon_db

router = Router()


@router.message(Command("weaponreload"))
async def weapon_database(message: types.Message):
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        await message.reply("Only bot admins can use this command.")
        return
    if _lock.locked():
        await message.reply("A data update is already running.")
        return
    async with _lock:
        status = await message.reply("Checking weapons in MongoDB…")
        try:
            count = await weapon_db.reload()
            from utils.weapons import load_weapons
            missing = sum(not item.get("image_url") for item in load_weapons().values())
            await status.edit_text(f"Weapon source: MongoDB\nLoaded: {count}\nWithout image URL: {missing}\nWeapon commands use the database cache. /update saves to MongoDB.", parse_mode=None)
        except Exception as error:
            await status.edit_text(f"Weapon database operation failed: {type(error).__name__}. Check MongoDB access and retry.", parse_mode=None)
