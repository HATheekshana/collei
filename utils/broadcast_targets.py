from utils import storage
"""
Tracks every private-chat user ID and every group/supergroup ID the bot has
been used in, so /broadcast can reach all of them.

Storage format (broadcast_targets.json):
{
    "users":  {"<user_id>":  {"name": "...", "username": "..."}, ...},
    "groups": {"<chat_id>":  {"title": "..."}, ...}
}
"""

import json
import logging
import os

from data.config import BROADCAST_TARGETS_FILE

_cache = None


def _load() -> dict:
    return storage.read("broadcast_targets", {"users": {}, "groups": {}})


def _save(data: dict) -> bool:
    return storage.save("broadcast_targets", data)


def record_user(user_id: int, name: str = "", username: str = "") -> bool:
    """
    Save a private-chat user ID if it isn't already known.
    Returns True if it was newly added, False if already known (or on
    failure to save).
    """
    data = _load()
    key = str(user_id)
    if key in data["users"]:
        return False
    data["users"][key] = {"name": name or "", "username": username or ""}
    return _save(data)


def record_group(chat_id: int, title: str = "") -> bool:
    """
    Save a group/supergroup chat ID if it isn't already known.
    Returns True if it was newly added, False if already known (or on
    failure to save).
    """
    data = _load()
    key = str(chat_id)
    if key in data["groups"]:
        return False
    data["groups"][key] = {"title": title or ""}
    return _save(data)


def remove_user(user_id: int) -> bool:
    data = _load()
    key = str(user_id)
    if key not in data["users"]:
        return False
    del data["users"][key]
    return _save(data)


def remove_group(chat_id: int) -> bool:
    data = _load()
    key = str(chat_id)
    if key not in data["groups"]:
        return False
    del data["groups"][key]
    return _save(data)


def get_all_user_ids() -> list:
    return [int(k) for k in _load()["users"].keys()]


def get_all_group_ids() -> list:
    return [int(k) for k in _load()["groups"].keys()]


def get_target_counts() -> tuple:
    data = _load()
    return len(data["users"]), len(data["groups"])