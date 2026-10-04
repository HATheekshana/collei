"""Artifact-only Mongo storage. Other bot sections retain their JSON stores."""
import os
import asyncio
from contextlib import contextmanager

@contextmanager
def collection():
    from pymongo import MongoClient
    uri = os.getenv("MONGO_URL")
    if not uri:
        raise ValueError("MONGO_URL is missing")
    with MongoClient(uri, serverSelectionTimeoutMS=8000, socketTimeoutMS=20000) as client:
        yield client[os.getenv("MONGO_TEST_DB", "collei_test")]["artifacts"]

def read_all():
    with collection() as col:
        return [doc["entry"] for doc in col.find({"schema": "artifact-v1"})]

def save(entry):
    from utils.helper import normalize_name
    key = "artifact:" + normalize_name(entry["name"])
    with collection() as col:
        old = col.find_one({"_id": key})
        merged = {**(old or {}).get("entry", {}), **entry}
        if entry.get("image_url"):
            merged["image_urls"] = [entry["image_url"]] + [
                u for u in merged.get("image_urls", []) if u != entry["image_url"]]
        col.replace_one({"_id": key}, {"_id": key, "schema": "artifact-v1", "entry": merged}, upsert=True)
        saved = col.find_one({"_id": key})
        if not saved or saved["entry"] != merged:
            raise RuntimeError("Artifact read-back did not match")
    return merged

async def reload():
    from utils import artifacts
    from utils.helper import normalize_name
    from data.search_items import SEARCH_ITEMS
    entries = await asyncio.to_thread(read_all)
    artifacts._artifact_info_cache = {normalize_name(e["name"]): e for e in entries}
    SEARCH_ITEMS.update({normalize_name(e["name"]): e["name"] for e in entries})
    return len(entries)
