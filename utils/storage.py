"""Pooled MongoDB store for remaining Collei datasets."""
import os
from copy import deepcopy
from threading import RLock
from functools import lru_cache

_lock = RLock()
_cache = {}

@lru_cache(maxsize=1)
def database():
    from pymongo import MongoClient
    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000,
                         connectTimeoutMS=8000, socketTimeoutMS=20000, maxPoolSize=10)
    return client[os.getenv("MONGO_TEST_DB", "collei_test")]

def read(section, default):
    with _lock:
        if section not in _cache:
            doc = database()[section].find_one({"_id": "live"})
            _cache[section] = deepcopy(doc["value"] if doc else default)
        return deepcopy(_cache[section])

def save(section, value):
    with _lock:
        database()[section].replace_one({"_id": "live"}, {"_id": "live", "value": value}, upsert=True)
        _cache[section] = deepcopy(value)
    return True

def ready():
    return bool(database()["storage_meta"].find_one({"_id": "all-db-active"}))

def clear():
    with _lock: _cache.clear()
