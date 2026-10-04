from utils import storage
import json
import logging
import os

from data.config import SPECIAL_MEDIA_FILE

# The three record categories exposed as buttons under /next and /current
CATEGORIES = ("abyss", "theatre", "stygian")

# Current-phase records and next-phase records are tracked as separate,
# independent image sets.
PHASES = ("current", "next")

LABELS = {
    "abyss": "Spiral Abyss",
    "theatre": "Imaginarium Theatre",
    "stygian": "Stygian Onslaught",
}

_cache: dict | None = None


def _key(phase: str, category: str) -> str:
    return f"{phase}:{category}"


def _invalidate_cache():
    global _cache
    _cache = None


def _default_data() -> dict:
    return {_key(phase, cat): [] for phase in PHASES for cat in CATEGORIES}


def load_special_media() -> dict:
    data = storage.read("endgame", {})
    for cat in CATEGORIES:
        if cat in data:
            data.setdefault(_key("current", cat), data.pop(cat))
    return {**_default_data(), **data}


def save_special_media(data: dict) -> bool:
    return storage.save("endgame", data)


def add_media(phase: str, category: str, file_id: str, image_url: str | None = None) -> bool:
    """Append one image (Telegram file_id, plus optional public image_url for
    inline-mode preview) to a phase+category. Multiple allowed."""
    data = load_special_media()
    entry = {"file_id": file_id}
    if image_url:
        entry["image_url"] = image_url
    data.setdefault(_key(phase, category), []).append(entry)
    return save_special_media(data)


def get_media(phase: str, category: str) -> list[dict]:
    return load_special_media().get(_key(phase, category), [])


def get_image_urls(phase: str, category: str) -> list[str]:
    """Public (imgbb) URLs only, for inline-mode preview cycling."""
    return [m["image_url"] for m in get_media(phase, category) if m.get("image_url")]


def delete_all(phase: str, category: str) -> int:
    """Delete every image stored for a phase+category. Returns how many were removed."""
    data = load_special_media()
    key = _key(phase, category)
    removed = len(data.get(key, []))
    data[key] = []
    save_special_media(data)
    return removed
