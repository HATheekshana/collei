from utils import storage
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
    return storage.read("bosses", [])


def save_bosses(bosses: list) -> bool:
    return storage.save("bosses", bosses)


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
