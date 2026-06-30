import json
import logging
import os

from data.config import GUIDES_FILE

_guides_cache: list | None = None


def _invalidate_cache():
    global _guides_cache
    _guides_cache = None


def load_guides() -> list:
    global _guides_cache
    if _guides_cache is not None:
        return _guides_cache

    if not os.path.isfile(GUIDES_FILE):
        _guides_cache = []
        return _guides_cache

    try:
        with open(GUIDES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _guides_cache = data if isinstance(data, list) else []
    except Exception:
        logging.exception("Failed to load guides.json")
        _guides_cache = []

    return _guides_cache


def save_guides(guides: list) -> bool:
    try:
        with open(GUIDES_FILE, "w", encoding="utf-8") as fh:
            json.dump(guides, fh, ensure_ascii=False, indent=2)
        _invalidate_cache()
        load_guides()
        return True
    except Exception:
        logging.exception("Failed to save guides.json")
        return False


def find_guides_for_character(character_key: str) -> list[dict]:
    """Return all guide entries whose character_key matches exactly."""
    key = character_key.lower().strip()
    return [g for g in load_guides() if g.get("character_key") == key]


def set_guide_file_id(filename: str, file_id: str) -> bool:
    guides = load_guides()
    for guide in guides:
        if guide.get("filename") == filename:
            guide["file_id"] = file_id
            return save_guides(guides)
    return False


def set_guide_image_url(filename: str, image_url: str) -> bool:
    """Save imgbb URL to a guide entry."""
    guides = load_guides()
    for guide in guides:
        if guide.get("filename") == filename:
            guide["image_url"] = image_url
            return save_guides(guides)
    return False


def get_guide_entry_by_filename(filename: str) -> dict | None:
    for guide in load_guides():
        if guide.get("filename") == filename:
            return guide
    return None