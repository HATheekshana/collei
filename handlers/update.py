import asyncio
import logging
from pathlib import Path
from aiogram import Router, types
from aiogram.filters import Command
from data.config import ADMIN_IDS
from utils.weapon_update import update_weapons
from utils.character_update import update_characters

router = Router()
_lock = asyncio.Lock()

@router.message(Command("update"))
async def update(message: types.Message):
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        await message.reply("Only bot admins can update data.")
        return
    args = (message.text or "").split()[1:]
    import re
    version = None
    extra_ids = []
    for arg in args:
        if re.fullmatch(r"1000\d{4}", arg):
            extra_ids.append(arg)
        elif version is None and re.fullmatch(r"\d+\.\d+(?:\.\d+)*", arg):
            version = arg
        else:
            await message.reply("Use /update, /update 7.1, or /update 7.1 10000136.")
            return
    if len(extra_ids)>10:
        await message.reply("Supply at most 10 character IDs per update.")
        return
    if _lock.locked():
        await message.reply("An update is already running.")
        return
    async with _lock:
        status = await message.reply("Updating weapons and character details…")
        async def progress(text):
            try: await status.edit_text(text)
            except Exception: logging.warning("Could not update progress message")
        results = []
        version_hints = []
        for section in ("Weapons", "Characters"):
            try:
                if section == "Weapons":
                    result = await update_weapons(progress=progress)
                    if result.get("version"):
                        version_hints.append(result["version"])
                    from utils import weapon_db
                    try:
                        await weapon_db.reload()
                    except Exception as error:
                        result["cache_warning"] = type(error).__name__ + ": saved data requires /weaponreload"
                else:
                    from utils import character_details
                    result = await update_characters(character_details.ROOT / "data/character_details.json",
                                                     progress, version, extra_ids=extra_ids, version_hints=version_hints)
                    character_details.records.cache_clear()
                    from utils.cards import load_cards
                    from utils.guides import load_guides
                    missing = sorted({str(item.get("character_key"))
                                      for item in load_cards()+load_guides()
                                      if item.get("character_key") and not character_details.lookup(str(item["character_key"]))})
                    if missing:
                        result.setdefault("warnings",[]).append(
                            "Cards/guides still without matching Cons/Skills: " + ", ".join(missing) +
                            ". Check the selected Nanoka version, failed imports and character names.")
            except Exception as error:
                result = {"error": type(error).__name__}
            results.append((section, result))
        from utils.update_report import pages
        from handlers.media import _raw_api_request
        import json
        report_pages = pages(results)
        try:
            await _raw_api_request(message.bot, "editMessageText", {
                "chat_id": status.chat.id, "message_id": status.message_id,
                "rich_message": {"html": report_pages[0]}})
            for page in report_pages[1:]:
                await _raw_api_request(message.bot, "sendRichMessage", {
                    "chat_id": message.chat.id, "rich_message": {"html": page},
                    "reply_parameters": {"message_id": message.message_id}})
        except Exception:
            logging.warning("Rich update report delivery failed")
            await status.edit_text("Update processing finished. Rich report delivery failed; the complete report is attached.", parse_mode=None)
        # Exact machine-readable details remain available even for very large reports.
        await message.reply_document(types.BufferedInputFile(
            json.dumps(dict(results), ensure_ascii=False, indent=2).encode(),
            filename="update-report.json"), caption="Complete update report")
