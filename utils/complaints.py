from utils import storage
"""
Tracks the link between a complaint posted in the support chat and the
original user/chat that sent it, so /answer knows where to deliver the
reply.

Storage format (complaints.json):
{
    "<support_message_id>": {
        "user_id": 123456,
        "user_name": "Jane Doe",
        "username": "janedoe",
        "chat_id": 123456,          # origin chat (private chat == user_id, or a group id)
        "chat_type": "private",     # "private" | "group" | "supergroup"
        "text": "the complaint text"
    },
    ...
}
"""

import json
import logging
import os

from data.config import COMPLAINTS_FILE

_cache = None


def _load() -> dict:
    return storage.read("complaints", {})


def _save(data: dict) -> bool:
    return storage.save("complaints", data)


def record_complaint(support_message_id: int, info: dict) -> bool:
    """Save the origin info for a complaint keyed by the id of the message
    the bot posted in the support chat."""
    data = _load()
    data[str(support_message_id)] = info
    return _save(data)


def get_complaint(support_message_id: int) -> dict | None:
    return _load().get(str(support_message_id))