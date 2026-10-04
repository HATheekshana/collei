import logging
import os
from aiogram import Bot
from data.config import (
    LOG_CHAT_ID,
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


def build_character_cache():
    """Compatibility hook; main loads the MongoDB snapshot asynchronously."""
    pass

async def resolve_character_media(bot: Bot, character_key: str) -> list[dict]:
    from utils.cards import find_cards_for_character
    from utils.guides import find_guides_for_character
    from data.search_items import SEARCH_ITEMS
    key = normalize_name(character_key)
    entries = find_cards_for_character(key) + find_guides_for_character(key)
    if not entries:
        for search_key, name in SEARCH_ITEMS.items():
            if normalize_name(name) == key:
                entries = find_cards_for_character(search_key) + find_guides_for_character(search_key)
                break
    return [{k: e[k] for k in ("image_url", "file_id") if e.get(k)}
            for e in entries if e.get("image_url") or e.get("file_id")]

async def resolve_character_file_ids(bot: Bot, character_key: str) -> list[str]:
    return [e.get("file_id") or e["image_url"] for e in await resolve_character_media(bot, character_key)]

def find_character_files(character_key: str) -> list[str]:
    """Character media never use local image folders."""
    return []


# ---------------------------------------------------------------------------
# Artifact lookups
# ---------------------------------------------------------------------------

def find_artifact_files(artifact: str) -> list:
    """Compatibility hook: artifacts never read local image files."""
    return []

