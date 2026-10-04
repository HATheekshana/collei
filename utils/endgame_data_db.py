"""Compressed MongoDB copies of upstream endgame JSON (icons remain local)."""
import json
import zlib
from pathlib import Path
from utils import storage

def key(path): return Path(path).name

def save(path, raw):
    # Decode before saving so an upstream HTML error cannot replace valid data.
    value = json.loads(raw)
    blob = zlib.compress(json.dumps(value, ensure_ascii=False).encode())
    storage.database()["endgame_data"].replace_one({"_id": key(path)}, {"_id": key(path), "blob": blob}, upsert=True)

def exists(path):
    return storage.database()["endgame_data"].find_one({"_id": key(path)}) is not None

def load(path):
    doc = storage.database()["endgame_data"].find_one({"_id": key(path)})
    if not doc: raise FileNotFoundError("Endgame data not in MongoDB: " + key(path))
    return json.loads(zlib.decompress(doc["blob"]))
