"""Character guides are read from the MongoDB snapshot, never JSON."""
from utils.character_media_db import load

def load_guides() -> list:
    return load("guides")

def find_guides_for_character(character_key: str) -> list[dict]:
    key = character_key.lower().strip()
    return [entry for entry in load_guides() if entry.get("character_key") == key]

def get_guide_entry_by_filename(filename: str) -> dict | None:
    return next((e for e in load_guides() if e.get("filename") == filename), None)
