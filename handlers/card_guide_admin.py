import logging
from uuid import uuid4
from html import escape

from aiogram import types

from data.config import ADMIN_IDS, MEDIA_CHANNEL
from utils.cards import load_cards
from utils.guides import load_guides
from utils import character_media_db
from utils.helper import normalize_name
from data.search_items import SEARCH_ITEMS

def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


# ---------------------------------------------------------------------------
# SEARCH_ITEMS runtime helpers
# ---------------------------------------------------------------------------

def _add_to_search_items(key: str, display_name: str) -> bool:
    """Register a search label; database loaders restore it after restart."""
    SEARCH_ITEMS[key] = display_name
    return True


def _remove_from_search_items(key: str) -> bool:
    """
    Remove a key from SEARCH_ITEMS but only if no cards or guides
    remain for that character.
    """
    cards  = [c for c in load_cards()  if c.get("character_key") == key]
    guides = [g for g in load_guides() if g.get("character_key") == key]
    if cards or guides:
        return False   # still has media — don't remove
    SEARCH_ITEMS.pop(key, None)
    return True


# ---------------------------------------------------------------------------
# Key / display-name resolution
# ---------------------------------------------------------------------------

def _resolve_character_key(raw: str) -> str | None:
    """Return an existing SEARCH_ITEMS key for the given name, or None."""
    norm = normalize_name(raw)
    if norm in SEARCH_ITEMS:
        return norm
    for key, display_name in SEARCH_ITEMS.items():
        if normalize_name(display_name) == norm:
            return key
    return None


def _make_key(display_name: str) -> str:
    """
    Derive a canonical key from a display name, e.g.
    'Hu Tao' -> 'hutao', 'Yae Miko' -> 'yaemiko'.
    """
    return normalize_name(display_name)


# ---------------------------------------------------------------------------
# /addcard  /addguide
# ---------------------------------------------------------------------------

async def _handle_add_media(message: types.Message, kind: str):
    """
    kind: "card" or "guide"

    Usage: reply to a photo with /addcard <character> or /addguide <character>

    If the character doesn't exist in SEARCH_ITEMS or the database yet it is
    created automatically (restored from MongoDB on restart).
    
    Uploads image to both Telegram channel (backup) and imgbb (rich slideshow).
    """
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            f"Usage: reply to a photo with /add{kind} <character name>\n"
            f"Example: /add{kind} Wriothesley"
        )
        return

    character_arg = parts[1].strip()
    character_key = _resolve_character_key(character_arg)
    created_new = False

    if not character_key:
        # Auto-create: derive key from the provided name
        character_key = _make_key(character_arg)
        display_name  = character_arg.title()
        created_new = True
        logging.info("Auto-created SEARCH_ITEMS entry: %s -> %s", character_key, display_name)
    else:
        display_name = SEARCH_ITEMS.get(character_key, character_arg.title())

    replied = message.reply_to_message
    if not replied or not replied.photo:
        await message.reply(
            f"Please reply to a photo message with /add{kind} <character name>.\n"
            f"Note: send the image as a photo, not as a file/document."
        )
        return

    photo = replied.photo[-1]
    status_msg = await message.reply(f"⏳ Uploading {kind}...")

    # Upload to Telegram channel
    try:
        sent = await message.bot.send_photo(
            chat_id=MEDIA_CHANNEL,
            photo=photo.file_id,
            caption=f"{kind.title()}: {display_name}",
        )
        channel_file_id = sent.photo[-1].file_id
    except Exception:
        logging.exception("Failed to send %s image to channel", kind)
        await status_msg.edit_text(
            "Failed to send the image to the storage channel. "
            "Make sure the bot is an admin in that channel."
        )
        return

    # Try to upload to imgbb (non-blocking - will show error if it fails)
    imgbb_url = None
    try:
        from utils.imgbb import upload_file_by_telegram_download, ImgBBUploadError
        try:
            imgbb_url = await upload_file_by_telegram_download(
                message.bot, photo.file_id, 
                filename=f"{display_name}_{photo.file_id[-8:]}.jpg"
            )
            logging.info(f"Successfully uploaded {kind} to imgbb: {imgbb_url}")
        except ImgBBUploadError as e:
            logging.warning(f"imgbb upload failed (will use Telegram fallback): {e}")
    except Exception as e:
        logging.warning(f"Error with imgbb upload: {e}")

    new_entry = {
        "name": display_name, "display_name": display_name,
        "filename": f"{character_key}_{uuid4().hex}.jpg",
        "character_key": character_key, "file_id": channel_file_id,
    }
    if imgbb_url:
        new_entry["image_url"] = imgbb_url
    try:
        await character_media_db.add("cards" if kind == "card" else "guides", new_entry)
    except Exception:
        logging.exception("Character media database save failed")
        await status_msg.edit_text("Image uploaded, but saving to MongoDB failed. Please retry.")
        return
    display_name = escape(display_name)

    new_tag = " (new character created)" if created_new else ""
    imgbb_status = " ✨ (with imgbb link)" if imgbb_url else " (Telegram storage)"
    await status_msg.edit_text(
        f"✅ {kind.title()} added for <b>{display_name}</b>{new_tag}.{imgbb_status}",
        parse_mode="HTML",
    )
    logging.info("%s added: %s -> file_id=%s, imgbb=%s", kind.title(), display_name, channel_file_id, imgbb_url or "none")


# ---------------------------------------------------------------------------
# /delcard  /delguide
# ---------------------------------------------------------------------------

async def _handle_del_media(message: types.Message, kind: str):
    """
    kind: "card" or "guide"

    Usage: /delcard <character>   — deletes ALL cards for that character
           /delguide <character>  — deletes ALL guides for that character

    Also removes the character from SEARCH_ITEMS if no media remains.
    """
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            f"Usage: /del{kind} <character name>\n"
            f"Example: /del{kind} Collei"
        )
        return

    character_arg = parts[1].strip()
    character_key = _resolve_character_key(character_arg)

    if not character_key:
        await message.reply(
            f'Character "{character_arg}" not found.'
        )
        return

    display_name = SEARCH_ITEMS.get(character_key, character_arg.title())

    try:
        removed = await character_media_db.delete_character("cards" if kind == "card" else "guides", character_key)
    except Exception:
        logging.exception("Character media database deletion failed")
        await message.reply("Could not delete media from MongoDB. Please retry.")
        return
    display_name = escape(display_name)

    if removed == 0:
        await message.reply(f"No {kind}s found for <b>{display_name}</b>.", parse_mode="HTML")
        return

    # Remove from SEARCH_ITEMS if nothing left for this character at all
    auto_removed = False
    if _remove_from_search_items(character_key):
        auto_removed = True

    extra = "\nCharacter also removed from search (no media left)." if auto_removed else ""
    await message.reply(
        f"🗑 Deleted {removed} {kind}(s) for <b>{display_name}</b>.{extra}",
        parse_mode="HTML",
    )
    logging.info("%s(s) deleted for %s (%d entries removed)", kind.title(), display_name, removed)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def handle_addcard_command(message: types.Message):
    await _handle_add_media(message, "card")

async def handle_addguide_command(message: types.Message):
    await _handle_add_media(message, "guide")

async def handle_delcard_command(message: types.Message):
    await _handle_del_media(message, "card")

async def handle_delguide_command(message: types.Message):
    await _handle_del_media(message, "guide")