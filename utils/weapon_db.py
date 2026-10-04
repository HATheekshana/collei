"""MongoDB is the authoritative weapon store; cache only for fast replies."""
import asyncio
import os
from contextlib import contextmanager


@contextmanager
def collection():
    from pymongo import MongoClient
    uri = os.getenv("MONGO_URL")
    if not uri:
        raise ValueError("MONGO_URL is required")
    with MongoClient(uri, serverSelectionTimeoutMS=8000, socketTimeoutMS=20000) as client:
        yield client[os.getenv("MONGO_TEST_DB", "collei_test")]["weapons"]


def validate(item):
    if not isinstance(item, dict) or not str(item.get("id", "")).isdigit() or not item.get("name"):
        raise ValueError("Weapon requires a numeric ID and name")
    return str(int(item["id"]))


def read_all():
    with collection() as col:
        entries = [doc["entry"] for doc in col.find({"schema": "weapon-v1"})]
    for item in entries:
        validate(item)
    return entries


def save_many(entries):
    saved, errors = set(), {}
    with collection() as col:
        for item in entries:
            wid = str(item.get("id", "unknown")) if isinstance(item, dict) else "unknown"
            try:
                wid = validate(item)
                key = "weapon:" + wid
                document = {"_id": key, "schema": "weapon-v1", "entry": item}
                col.replace_one({"_id": key}, document, upsert=True)
                actual = col.find_one({"_id": key})
                if not actual or actual.get("schema") != "weapon-v1":
                    raise RuntimeError("Read-back verification failed")
                if actual.get("entry") != item:
                    raise RuntimeError("Read-back verification failed")
                saved.add(wid)
            except Exception as error:
                errors[wid] = type(error).__name__
    return saved, errors


async def reload():
    entries = await asyncio.to_thread(read_all)
    from utils import weapons
    from utils.helper import normalize_name
    from data.search_items import SEARCH_ITEMS
    snapshot = {normalize_name(item["name"]): item for item in entries}
    for key in weapons._weapons_cache:
        if key not in snapshot:
            SEARCH_ITEMS.pop(key, None)
    weapons._weapons_cache = snapshot
    SEARCH_ITEMS.update(weapons.weapon_search_items())
    return len(entries)
