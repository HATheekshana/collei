import json
import logging
import os

from utils.helper import normalize_name

BOSSES_FILE = "bosses.json"

_boss_cache: list | None = None


def _invalidate_cache():
    global _boss_cache
    _boss_cache = None


def load_bosses() -> list:
    global _boss_cache
    if _boss_cache is not None:
        return _boss_cache

    if not os.path.isfile(BOSSES_FILE):
        _boss_cache = []
        return _boss_cache

    try:
        with open(BOSSES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _boss_cache = data if isinstance(data, list) else []
    except Exception:
        logging.exception("Failed to load bosses.json")
        _boss_cache = []

    return _boss_cache


def save_bosses(bosses: list) -> bool:
    try:
        with open(BOSSES_FILE, "w", encoding="utf-8") as fh:
            json.dump(bosses, fh, ensure_ascii=False, indent=2)
        _invalidate_cache()
        load_bosses()
        return True
    except Exception:
        logging.exception("Failed to save bosses.json")
        return False


def find_boss(query: str) -> dict | None:
    """Return the first boss whose name starts with the normalized query."""
    norm = normalize_name(query)
    for boss in load_bosses():
        if normalize_name(boss.get("name", "")).startswith(norm):
            return boss
    return None


def set_boss_file_id(boss_name: str, file_id: str) -> bool:
    """Set the Telegram file_id for a boss and persist to disk."""
    bosses = load_bosses()
    norm = normalize_name(boss_name)

    for boss in bosses:
        if normalize_name(boss.get("name", "")) == norm:
            boss["file_id"] = file_id
            return save_bosses(bosses)

    # Boss not found — create a new entry
    bosses.append({"name": boss_name, "file_id": file_id})
    return save_bosses(bosses)


def get_boss_names_for_search() -> dict[str, str]:
    """Return {key: display_name} dict for all bosses, usable in SEARCH_ITEMS style."""
    result = {}
    for boss in load_bosses():
        name = boss.get("name", "")
        if not name:
            continue
        # Use first word (lowercased) as the short key
        key = normalize_name(name.split()[0])
        result[key] = name
    return result