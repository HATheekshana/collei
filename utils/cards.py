"""Character cards are read from the MongoDB snapshot, never JSON."""
from utils.character_media_db import load

def load_cards() -> list:
    return load("cards")

def find_cards_for_character(character_key: str) -> list[dict]:
    key = character_key.lower().strip()
    return [entry for entry in load_cards() if entry.get("character_key") == key]

def get_card_entry_by_filename(filename: str) -> dict | None:
    return next((e for e in load_cards() if e.get("filename") == filename), None)
