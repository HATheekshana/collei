from utils import storage
import json
import logging
import os

from data.config import BANNED_USERS_FILE

_cache = None


def _load() -> set[int]:
    return {int(x) for x in storage.read("banned_users", {"users": []})["users"]}


def _save(user_ids: set[int]) -> bool:
    return storage.save("banned_users", {"users": sorted(user_ids)})


def is_banned(user_id: int) -> bool:
    return user_id in _load()


def ban_user(user_id: int) -> bool:
    user_ids = _load()
    if user_id in user_ids:
        return False
    return _save(user_ids | {user_id})


def unban_user(user_id: int) -> bool:
    user_ids = _load()
    if user_id not in user_ids:
        return False
    return _save(user_ids - {user_id})
