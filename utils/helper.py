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
# Telegram-channel upload (fallback path, also used by sync)
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
            wait = e.retry_after + 1
            logging.warning(
                "Rate-limited on %s — waiting %d s (attempt %d/5)",
                local_path, wait, attempt + 1,
            )
            await asyncio.sleep(wait)
    return await bot.send_photo(
        chat_id=MEDIA_CHANNEL,
        photo=FSInputFile(local_path),
        caption=caption,
    )


# ---------------------------------------------------------------------------
# Startup: upload any local files missing an imgBB URL (or, failing that,
# a Telegram file_id) — then delete the local copy.
# ---------------------------------------------------------------------------

async def sync_media_to_telegram(bot: Bot) -> None:
    """
    Called once at startup. Walks cards.json and guides.json; for every entry
    where image_url is null but the local file exists on disk:
      1. Tries to upload to imgBB -> saves image_url.
      2. If imgBB fails, falls back to uploading to MEDIA_CHANNEL -> file_id.
      3. Deletes the local file from the VPS either way (once we have a URL
         or a file_id).

    Entries that already have an image_url are skipped.
    Entries with no image_url, no file_id, AND no local file are logged.
    """
    import asyncio
    from utils.cards import load_cards, set_card_image_url, set_card_file_id
    from utils.guides import load_guides, set_guide_image_url, set_guide_file_id
    from utils.imgbb import upload_file_to_imgbb, ImgBBUploadError

    uploaded_imgbb = 0
    uploaded_tg = 0
    skipped = 0
    missing = 0

    async def _process(entry, folder, set_url_fn, set_fid_fn, kind):
        nonlocal uploaded_imgbb, uploaded_tg, skipped, missing

        if entry.get("image_url"):
            skipped += 1
            return

        filename = entry.get("filename", "")
        if not filename:
            return

        local_path = os.path.join(folder, filename)
        if not os.path.isfile(local_path):
            if not entry.get("file_id"):
                logging.warning("%s has no image_url, no file_id, no local file: %s", kind, filename)
                missing += 1
            return

        # 1. Try imgBB first
        try:
            url = await upload_file_to_imgbb(local_path)
            set_url_fn(filename, url)
            os.remove(local_path)
            logging.info("Uploaded %s to imgBB and deleted local file: %s", kind, local_path)
            uploaded_imgbb += 1
            await asyncio.sleep(0.3)
            return
        except ImgBBUploadError as e:
            logging.warning("imgBB upload failed for %s (%s), falling back to Telegram channel", local_path, e)

        # 2. Fallback: Telegram channel
        try:
            sent = await _upload_photo_with_retry(bot, local_path, f"{kind.title()}: {entry.get('name', filename)}")
            file_id = sent.photo[-1].file_id
            set_fid_fn(filename, file_id)
            os.remove(local_path)
            logging.info("Uploaded %s to Telegram channel and deleted local file: %s", kind, local_path)
            uploaded_tg += 1
            await asyncio.sleep(0.5)
        except Exception:
            logging.exception("Both imgBB and Telegram upload failed for %s: %s", kind, local_path)

    for entry in load_cards():
        await _process(entry, CARDS_FOLDER, set_card_image_url, set_card_file_id, "card")

    for entry in load_guides():
        await _process(entry, GUIDES_FOLDER, set_guide_image_url, set_guide_file_id, "guide")

    logging.info(
        "sync_media_to_telegram done — imgBB: %d, Telegram fallback: %d, already done: %d, missing: %d",
        uploaded_imgbb, uploaded_tg, skipped, missing,
    )
    await send_log(
        bot,
        f"📦 Media sync complete\n"
        f"✅ Uploaded to imgBB: {uploaded_imgbb}\n"
        f"📤 Uploaded to Telegram (fallback): {uploaded_tg}\n"
        f"⏭ Already done: {skipped}\n"
        f"⚠️ Missing: {missing}",
    )


# ---------------------------------------------------------------------------
# Backwards-compat stub
# ---------------------------------------------------------------------------

def build_character_cache():
    pass


# ---------------------------------------------------------------------------
# Per-request: resolve image sources for a character (used by handlers)
# Returns a list of dicts: {"image_url": ...} or {"file_id": ...}
# ---------------------------------------------------------------------------

async def resolve_character_media(bot: Bot, character_key: str) -> list[dict]:
    """
    Returns a list of media sources (imgBB URL preferred, Telegram file_id
    fallback) for all cards + guides matching character_key.
    Uploads on the spot (imgBB first, then Telegram) if an entry still only
    has a local file.
    """
    from utils.cards import find_cards_for_character, set_card_image_url, set_card_file_id
    from utils.guides import find_guides_for_character, set_guide_image_url, set_guide_file_id
    from utils.imgbb import upload_file_to_imgbb, ImgBBUploadError
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

    results: list[dict] = []

    for entry in entries:
        filename = entry.get("filename", "")
        image_url = entry.get("image_url")
        file_id = entry.get("file_id")
        source = entry.get("source")

        if image_url:
            results.append({"image_url": image_url})
            continue
        if file_id:
            results.append({"file_id": file_id})
            continue

        folder = CARDS_FOLDER if source == "cards" else GUIDES_FOLDER
        local_path = os.path.join(folder, filename)

        if not os.path.isfile(local_path):
            logging.warning("Missing local file and no media for %s/%s", source, filename)
            continue

        # Try imgBB first
        try:
            url = await upload_file_to_imgbb(local_path)
            if source == "cards":
                set_card_image_url(filename, url)
            else:
                set_guide_image_url(filename, url)
            try:
                os.remove(local_path)
            except Exception:
                logging.exception("Could not delete local file %s", local_path)
            results.append({"image_url": url})
            continue
        except ImgBBUploadError as e:
            logging.warning("imgBB upload failed for %s (%s), falling back to Telegram", local_path, e)

        # Fallback: Telegram channel
        try:
            sent = await _upload_photo_with_retry(bot, local_path, f"{source.title()}: {entry.get('name', filename)}")
            new_file_id = sent.photo[-1].file_id
            if source == "cards":
                set_card_file_id(filename, new_file_id)
            else:
                set_guide_file_id(filename, new_file_id)
            try:
                os.remove(local_path)
            except Exception:
                logging.exception("Could not delete local file %s", local_path)
            results.append({"file_id": new_file_id})
        except Exception:
            logging.exception("Both imgBB and Telegram upload failed for %s", local_path)

    return results


# Backwards-compat: some older code may still import this name expecting
# a flat list of file_ids. Kept for safety; prefer resolve_character_media.
async def resolve_character_file_ids(bot: Bot, character_key: str) -> list[str]:
    media = await resolve_character_media(bot, character_key)
    return [m["file_id"] for m in media if "file_id" in m]


# ---------------------------------------------------------------------------
# Sync find_character_files for inline.py (returns local paths still on disk)
# ---------------------------------------------------------------------------

def find_character_files(character_key: str) -> list[str]:
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