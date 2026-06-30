import logging
import os
from aiogram import Bot
from data.config import (
    LOG_CHAT_ID,
    ARTIFACTS_FOLDER,
    ARTIFACTS_INFO_FILE,
    GUIDES_FOLDER,
    CARDS_FOLDER,
    MEDIA_CHANNEL,
)

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

async def send_log(bot: Bot, text: str):
    try:
        if not LOG_CHAT_ID:
            logging.info("LOG_CHAT_ID not set; skipping send_log")
            return
        await bot.send_message(chat_id=LOG_CHAT_ID, text=text)
    except Exception:
        logging.exception("Failed to send log message")


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "").replace(" ", "")


# ---------------------------------------------------------------------------
# Startup: upload any local files that are missing a Telegram file_id
# ---------------------------------------------------------------------------

async def _upload_photo_with_retry(bot: Bot, local_path: str, caption: str):
    """
    Upload a photo to MEDIA_CHANNEL, honouring Telegram flood-wait replies.
    Retries up to 5 times; raises on persistent failure.
    """
    import asyncio
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.types import FSInputFile

    for attempt in range(5):
        try:
            return await bot.send_photo(
                chat_id=MEDIA_CHANNEL,
                photo=FSInputFile(local_path),
                caption=caption,
            )
        except TelegramRetryAfter as e:
            wait = e.retry_after + 1          # +1 s safety buffer
            logging.warning(
                "Rate-limited on %s — waiting %d s (attempt %d/5)",
                local_path, wait, attempt + 1,
            )
            await asyncio.sleep(wait)
    # Final attempt — let the exception propagate
    return await bot.send_photo(
        chat_id=MEDIA_CHANNEL,
        photo=FSInputFile(local_path),
        caption=caption,
    )


async def sync_media_to_telegram(bot: Bot) -> None:
    """
    Called once at startup. Walks cards.json and guides.json; for every entry
    where file_id is null but the local file exists on disk:
      1. Uploads the file to MEDIA_CHANNEL as a photo (retrying on flood-wait).
      2. Saves the returned file_id back into the JSON.
      3. Deletes the local file from the VPS.

    Entries that already have a file_id are skipped (already uploaded).
    Entries with no file_id AND no local file are logged as a warning.
    """
    import asyncio
    from utils.cards import load_cards, set_card_file_id
    from utils.guides import load_guides, set_guide_file_id

    uploaded = 0
    skipped = 0
    missing = 0

    # --- Cards ---
    for entry in load_cards():
        if entry.get("file_id"):
            skipped += 1
            continue

        filename = entry.get("filename", "")
        if not filename:
            continue

        local_path = os.path.join(CARDS_FOLDER, filename)
        if not os.path.isfile(local_path):
            logging.warning("Card has no file_id and no local file: %s", filename)
            missing += 1
            continue

        try:
            sent = await _upload_photo_with_retry(
                bot, local_path, f"Card: {entry.get('name', filename)}"
            )
            file_id = sent.photo[-1].file_id
            set_card_file_id(filename, file_id)
            os.remove(local_path)
            logging.info("Uploaded card and deleted local file: %s", local_path)
            uploaded += 1
            await asyncio.sleep(0.5)   # gentle pace between uploads
        except Exception:
            logging.exception("Failed to upload card: %s", local_path)

    # --- Guides ---
    for entry in load_guides():
        if entry.get("file_id"):
            skipped += 1
            continue

        filename = entry.get("filename", "")
        if not filename:
            continue

        local_path = os.path.join(GUIDES_FOLDER, filename)
        if not os.path.isfile(local_path):
            logging.warning("Guide has no file_id and no local file: %s", filename)
            missing += 1
            continue

        try:
            sent = await _upload_photo_with_retry(
                bot, local_path, f"Guide: {entry.get('name', filename)}"
            )
            file_id = sent.photo[-1].file_id
            set_guide_file_id(filename, file_id)
            os.remove(local_path)
            logging.info("Uploaded guide and deleted local file: %s", local_path)
            uploaded += 1
            await asyncio.sleep(0.5)   # gentle pace between uploads
        except Exception:
            logging.exception("Failed to upload guide: %s", local_path)

    logging.info(
        "sync_media_to_telegram done — uploaded: %d, already had file_id: %d, missing locally: %d",
        uploaded, skipped, missing,
    )
    await send_log(
        bot,
        f"📦 Media sync complete\n"
        f"✅ Uploaded: {uploaded}\n"
        f"⏭ Already cached: {skipped}\n"
        f"⚠️ Missing (no file + no id): {missing}",
    )


# ---------------------------------------------------------------------------
# Backwards-compat stub (bot.py calls this synchronously at startup)
# ---------------------------------------------------------------------------

def build_character_cache():
    """No-op — kept so existing callers don't break."""
    pass


# ---------------------------------------------------------------------------
# Per-request: resolve file_ids for a character (used by handlers)
# ---------------------------------------------------------------------------

async def resolve_character_file_ids(bot: Bot, character_key: str) -> list[str]:
    """
    Returns Telegram file_ids for all cards + guides matching character_key.
    If an entry still lacks a file_id (e.g. uploaded after startup), it
    uploads on the spot, saves the id, and deletes the local file.
    """
    from utils.cards import find_cards_for_character, set_card_file_id
    from utils.guides import find_guides_for_character, set_guide_file_id
    from aiogram.types import FSInputFile
    from data.search_items import SEARCH_ITEMS

    key = normalize_name(character_key)

    cards_found = find_cards_for_character(key)
    guides_found = find_guides_for_character(key)

    if not cards_found and not guides_found:
        for search_key, display_name in SEARCH_ITEMS.items():
            if normalize_name(display_name) == key:
                cards_found = find_cards_for_character(search_key)
                guides_found = find_guides_for_character(search_key)
                break

    entries = []
    for c in cards_found:
        entries.append({"source": "cards", **c})
    for g in guides_found:
        entries.append({"source": "guides", **g})

    file_ids: list[str] = []

    for entry in entries:
        filename = entry.get("filename", "")
        file_id = entry.get("file_id")
        source = entry.get("source")

        if file_id:
            file_ids.append(file_id)
            continue

        folder = CARDS_FOLDER if source == "cards" else GUIDES_FOLDER
        local_path = os.path.join(folder, filename)

        if not os.path.isfile(local_path):
            logging.warning("Missing local file and no file_id for %s/%s", source, filename)
            continue

        try:
            sent = await bot.send_photo(
                chat_id=MEDIA_CHANNEL,
                photo=FSInputFile(local_path),
                caption=f"{source.title()}: {entry.get('name', filename)}",
            )
            new_file_id = sent.photo[-1].file_id

            if source == "cards":
                set_card_file_id(filename, new_file_id)
            else:
                set_guide_file_id(filename, new_file_id)

            try:
                os.remove(local_path)
                logging.info("Uploaded and deleted local file: %s", local_path)
            except Exception:
                logging.exception("Could not delete local file %s", local_path)

            file_ids.append(new_file_id)

        except Exception:
            logging.exception("Failed to upload %s to MEDIA_CHANNEL", local_path)

    return file_ids


async def resolve_character_media(bot: Bot, character_key: str) -> list[dict]:
    """
    Returns media items for all cards + guides matching character_key.
    Each item has both image_url (imgbb) and file_id (Telegram) for fallback.
    
    Returns:
        List of dicts: {"image_url": "...", "file_id": "...", ...}
    """
    from utils.cards import find_cards_for_character, set_card_file_id
    from utils.guides import find_guides_for_character, set_guide_file_id
    from aiogram.types import FSInputFile
    from data.search_items import SEARCH_ITEMS

    key = normalize_name(character_key)
    logging.info(f"resolve_character_media: Looking up character_key='{character_key}' normalized='{key}'")

    cards_found = find_cards_for_character(key)
    guides_found = find_guides_for_character(key)
    logging.info(f"  Found {len(cards_found)} cards and {len(guides_found)} guides for key '{key}'")

    if not cards_found and not guides_found:
        logging.info(f"  No cards/guides found, checking SEARCH_ITEMS...")
        for search_key, display_name in SEARCH_ITEMS.items():
            if normalize_name(display_name) == key:
                logging.info(f"    Found search key: {search_key}")
                cards_found = find_cards_for_character(search_key)
                guides_found = find_guides_for_character(search_key)
                logging.info(f"    After search_key lookup: {len(cards_found)} cards, {len(guides_found)} guides")
                break

    entries = []
    for c in cards_found:
        entries.append({"source": "cards", **c})
    for g in guides_found:
        entries.append({"source": "guides", **g})

    logging.info(f"  Total entries to process: {len(entries)}")

    media_items: list[dict] = []

    for entry in entries:
        filename = entry.get("filename", "")
        file_id = entry.get("file_id")
        image_url = entry.get("image_url")
        source = entry.get("source")

        logging.info(f"    Processing {source}/{filename}: file_id={'✓' if file_id else '✗'}, image_url={'✓' if image_url else '✗'}")

        # Build media item with available URLs
        media_item = {}
        
        if image_url:
            media_item["image_url"] = image_url
        
        if file_id:
            media_item["file_id"] = file_id
        else:
            # No file_id yet - try to upload to Telegram
            folder = CARDS_FOLDER if source == "cards" else GUIDES_FOLDER
            local_path = os.path.join(folder, filename)

            if os.path.isfile(local_path):
                try:
                    sent = await bot.send_photo(
                        chat_id=MEDIA_CHANNEL,
                        photo=FSInputFile(local_path),
                        caption=f"{source.title()}: {entry.get('name', filename)}",
                    )
                    new_file_id = sent.photo[-1].file_id
                    media_item["file_id"] = new_file_id

                    if source == "cards":
                        set_card_file_id(filename, new_file_id)
                    else:
                        set_guide_file_id(filename, new_file_id)

                    try:
                        os.remove(local_path)
                        logging.info("Uploaded and deleted local file: %s", local_path)
                    except Exception:
                        logging.exception("Could not delete local file %s", local_path)

                except Exception:
                    logging.exception("Failed to upload %s to MEDIA_CHANNEL", local_path)
            else:
                logging.warning("Missing local file and no file_id for %s/%s", source, filename)

        # Add to results if we have at least one way to retrieve the image
        if media_item:
            media_items.append(media_item)

    logging.info(f"  Returning {len(media_items)} media items with URLs")
    return media_items


# ---------------------------------------------------------------------------
# Sync find_character_files for inline.py (returns local paths still on disk)
# ---------------------------------------------------------------------------

def find_character_files(character_key: str) -> list[str]:
    """
    Returns sorted relative paths (e.g. 'cards/Albedo.png') for entries
    that still have a local file. Entries already uploaded (file deleted)
    won't appear here — use resolve_character_file_ids for those.
    """
    from utils.cards import find_cards_for_character
    from utils.guides import find_guides_for_character

    key = normalize_name(character_key)
    paths: list[str] = []

    for entry in find_cards_for_character(key):
        filename = entry.get("filename", "")
        if filename and os.path.isfile(os.path.join(CARDS_FOLDER, filename)):
            paths.append(os.path.join("cards", filename).replace("\\", "/"))

    for entry in find_guides_for_character(key):
        filename = entry.get("filename", "")
        if filename and os.path.isfile(os.path.join(GUIDES_FOLDER, filename)):
            paths.append(os.path.join("guides", filename).replace("\\", "/"))

    return sorted(paths)


# ---------------------------------------------------------------------------
# Artifact lookups
# ---------------------------------------------------------------------------

def find_artifact_files(artifact: str) -> list:
    files = []
    normalized_artifact = normalize_name(artifact)

    if not os.path.isdir(ARTIFACTS_FOLDER):
        return files

    for fname in os.listdir(ARTIFACTS_FOLDER):
        if fname == os.path.basename(ARTIFACTS_INFO_FILE):
            continue
        name_without_ext = os.path.splitext(fname)[0]
        normalized_file = normalize_name(name_without_ext)
        if normalized_file.startswith(normalized_artifact):
            files.append(os.path.join(ARTIFACTS_FOLDER, fname))

    return sorted(files)