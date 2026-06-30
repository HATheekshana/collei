import json
import logging
import os

from data.config import CARDS_FILE

_cards_cache: list | None = None


def _invalidate_cache():
    global _cards_cache
    _cards_cache = None


def load_cards() -> list:
    global _cards_cache
    if _cards_cache is not None:
        return _cards_cache

    if not os.path.isfile(CARDS_FILE):
        _cards_cache = []
        return _cards_cache

    try:
        with open(CARDS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _cards_cache = data if isinstance(data, list) else []
    except Exception:
        logging.exception("Failed to load cards.json")
        _cards_cache = []

    return _cards_cache


def save_cards(cards: list) -> bool:
    try:
        with open(CARDS_FILE, "w", encoding="utf-8") as fh:
            json.dump(cards, fh, ensure_ascii=False, indent=2)
        _invalidate_cache()
        load_cards()
        return True
    except Exception:
        logging.exception("Failed to save cards.json")
        return False


def find_cards_for_character(character_key: str) -> list[dict]:
    """Return all card entries whose character_key matches exactly."""
    key = character_key.lower().strip()
    return [c for c in load_cards() if c.get("character_key") == key]


def set_card_file_id(filename: str, file_id: str) -> bool:
    cards = load_cards()
    for card in cards:
        if card.get("filename") == filename:
            card["file_id"] = file_id
            return save_cards(cards)
    return False


def set_card_image_url(filename: str, image_url: str) -> bool:
    """Save imgbb URL to a card entry."""
    cards = load_cards()
    for card in cards:
        if card.get("filename") == filename:
            card["image_url"] = image_url
            return save_cards(cards)
    return False


def get_card_entry_by_filename(filename: str) -> dict | None:
    for card in load_cards():
        if card.get("filename") == filename:
            return card
    return None