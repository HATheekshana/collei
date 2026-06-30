import logging
import os
import re

from aiogram import types

from data.config import ADMIN_IDS, MEDIA_CHANNEL, CARDS_FILE, GUIDES_FILE
from utils.cards import load_cards, save_cards
from utils.guides import load_guides, save_guides
from utils.helper import normalize_name
from data.search_items import SEARCH_ITEMS

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}

SEARCH_ITEMS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "search_items.py")


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


# ---------------------------------------------------------------------------
# SEARCH_ITEMS runtime helpers
# ---------------------------------------------------------------------------

def _add_to_search_items(key: str, display_name: str) -> bool:
    """
    Add key -> display_name to the in-memory SEARCH_ITEMS dict AND persist it
    to data/search_items.py so it survives restarts.
    """
    SEARCH_ITEMS[key] = display_name
    return _save_search_items()


def _remove_from_search_items(key: str) -> bool:
    """
    Remove a key from SEARCH_ITEMS and persist, but only if no cards or guides
    remain for that character.
    """
    cards  = [c for c in load_cards()  if c.get("character_key") == key]
    guides = [g for g in load_guides() if g.get("character_key") == key]
    if cards or guides:
        return False   # still has media — don't remove
    SEARCH_ITEMS.pop(key, None)
    return _save_search_items()


def _save_search_items() -> bool:
    """Rewrite data/search_items.py from the current in-memory SEARCH_ITEMS."""
    try:
        path = os.path.normpath(SEARCH_ITEMS_PATH)
        lines = ["SEARCH_ITEMS = {\n"]
        for k, v in sorted(SEARCH_ITEMS.items()):
            lines.append(f'    {k!r}: {v!r},\n')
        lines.append("}\n")
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        return True
    except Exception:
        logging.exception("Failed to save search_items.py")
        return False


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

    If the character doesn't exist in SEARCH_ITEMS or the JSON yet it is
    created automatically (in-memory + persisted to search_items.py).
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
        if not _add_to_search_items(character_key, display_name):
            await message.reply(
                f"⚠️ Could not save new character \"{display_name}\" to search_items.py. "
                f"Check logs."
            )
            return
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

    image_url: str | None = None
    channel_file_id: str | None = None

    # 1. Try imgBB first — download the photo bytes from Telegram, then upload.
    try:
        from io import BytesIO
        from utils.imgbb import upload_to_imgbb, ImgBBUploadError

        buf = BytesIO()
        await message.bot.download(photo.file_id, destination=buf)
        buf.seek(0)
        image_url = await upload_to_imgbb(buf.read(), filename=display_name)
    except ImgBBUploadError as e:
        logging.warning("imgBB upload failed for /add%s %s (%s), falling back to Telegram channel", kind, display_name, e)
    except Exception:
        logging.exception("Unexpected error during imgBB upload for /add%s %s", kind, display_name)

    # 2. Fallback: Telegram channel (only if imgBB failed)
    if not image_url:
        try:
            sent = await message.bot.send_photo(
                chat_id=MEDIA_CHANNEL,
                photo=photo.file_id,
                caption=f"{kind.title()}: {display_name}",
            )
            channel_file_id = sent.photo[-1].file_id
        except Exception:
            logging.exception("Failed to send %s image to channel", kind)
            await message.reply(
                "Failed to upload to imgBB AND to the Telegram storage channel. "
                "Check IMGBB_API_KEY and that the bot is an admin in the channel."
            )
            return

    entries = load_cards() if kind == "card" else load_guides()
    existing_count = sum(1 for e in entries if e.get("character_key") == character_key)
    suffix = f"_{existing_count + 1}" if existing_count else ""
    synthetic_filename = f"{display_name}{suffix}.jpg"

    new_entry = {
        "name": f"{display_name}{(' ' + str(existing_count + 1)) if existing_count else ''}",
        "filename": synthetic_filename,
        "character_key": character_key,
        "image_url": image_url,
        "file_id": channel_file_id,
    }
    entries.append(new_entry)

    saved = save_cards(entries) if kind == "card" else save_guides(entries)
    if not saved:
        await message.reply(
            f"Image uploaded but failed to save to {kind}s.json. Check logs."
        )
        return

    new_tag = " (new character created)" if created_new else ""
    storage_note = "imgBB (public URL)" if image_url else "Telegram channel (file_id fallback)"
    await message.reply(
        f"✅ {kind.title()} added for <b>{display_name}</b>{new_tag}.\n"
        f"Stored via {storage_note} — no file written to the server.",
        parse_mode="HTML",
    )
    logging.info("%s added: %s -> %s", kind.title(), display_name, image_url or channel_file_id)



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

    if kind == "card":
        entries   = load_cards()
        remaining = [e for e in entries if e.get("character_key") != character_key]
        removed   = len(entries) - len(remaining)
        saved     = save_cards(remaining)
    else:
        entries   = load_guides()
        remaining = [e for e in entries if e.get("character_key") != character_key]
        removed   = len(entries) - len(remaining)
        saved     = save_guides(remaining)

    if not saved:
        await message.reply(f"Failed to save {kind}s.json after deletion. Check logs.")
        return

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