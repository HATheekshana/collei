"""MongoDB character media, with a read snapshot for fast command/inline replies."""
import asyncio
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import os
import time

_cache = {"cards": None, "guides": None}
_lock = asyncio.Lock()

@contextmanager
def collection(kind):
    if kind not in _cache:
        raise ValueError("Unknown character media section")
    from pymongo import MongoClient
    with MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000,
                     socketTimeoutMS=20000) as client:
        yield client[os.getenv("MONGO_TEST_DB", "collei_test")][kind]

def validate(entry):
    if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k].strip()
                                             for k in ("filename", "character_key")):
        raise ValueError("Media requires filename and character_key")
    if not (entry.get("file_id") or entry.get("image_url")):
        raise ValueError("Media requires a Telegram file ID or public image URL")
    return "media:" + hashlib.sha256(entry["filename"].encode()).hexdigest()

def read_all(kind):
    with collection(kind) as col:
        entries = [doc["entry"] for doc in col.find({"schema": "character-media-v1"}).sort([("position", 1), ("_id", 1)])]
    for entry in entries:
        validate(entry)
    return entries

def load(kind):
    if _cache[kind] is None:
        raise RuntimeError("Character media database has not loaded")
    return deepcopy(_cache[kind])

def publish(kind, entries):
    from data.search_items import SEARCH_ITEMS
    _cache[kind] = deepcopy(entries)
    for entry in entries:
        if entry.get("display_name"):
            SEARCH_ITEMS[entry["character_key"]] = entry["display_name"]
        else:
            SEARCH_ITEMS.setdefault(entry["character_key"], entry["character_key"].title())

async def reload():
    async with _lock:
        snapshots = await asyncio.to_thread(lambda: {k: read_all(k) for k in _cache})
        for kind, entries in snapshots.items():
            publish(kind, entries)
        return {k: len(v) for k, v in snapshots.items()}

def write_one(kind, entry, *, insert=False, position=None):
    key = validate(entry)
    doc = {"_id": key, "schema": "character-media-v1", "entry": deepcopy(entry), "position": time.time_ns() if position is None else position}
    with collection(kind) as col:
        if insert:
            col.insert_one(doc)
        else:
            col.replace_one({"_id": key}, doc, upsert=True)
        if col.find_one({"_id": key}) != doc:
            raise RuntimeError("Media read-back verification failed")
    return entry

async def add(kind, entry):
    async with _lock:
        await asyncio.to_thread(write_one, kind, entry, insert=True)
        publish(kind, await asyncio.to_thread(read_all, kind))

async def delete_character(kind, key):
    def remove():
        with collection(kind) as col:
            return col.delete_many({"schema": "character-media-v1", "entry.character_key": key}).deleted_count
    async with _lock:
        count = await asyncio.to_thread(remove)
        publish(kind, await asyncio.to_thread(read_all, kind))
        return count
