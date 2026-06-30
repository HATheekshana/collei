#!/usr/bin/env python3
"""
Initialize cards.json and guides.json from existing local files.

Scans cards/ and guides/ directories and creates JSON metadata files
with structure: {name, filename, character_key, file_id, image_url}
"""

import os
import json
import logging
from data.config import CARDS_FOLDER, GUIDES_FOLDER, CARDS_FILE, GUIDES_FILE
from utils.helper import normalize_name

logging.basicConfig(level=logging.INFO)


def extract_character_key_from_filename(filename: str) -> str:
    """Extract character key from filename like 'Albedo_5.5.jpg' -> 'albedo'"""
    # Remove extension
    name_part = os.path.splitext(filename)[0]
    # Split on underscore and take first part (or use whole name)
    # e.g. "Albedo_5.5" -> "Albedo" or "Amber_Guide" -> "Amber"
    parts = name_part.split('_')
    if parts:
        return normalize_name(parts[0])
    return normalize_name(name_part)


def init_cards_json():
    """Create cards.json from local cards/ directory"""
    if os.path.isfile(CARDS_FILE):
        logging.info(f"{CARDS_FILE} already exists, skipping")
        return
    
    if not os.path.isdir(CARDS_FOLDER):
        logging.warning(f"{CARDS_FOLDER} directory not found")
        return
    
    cards = []
    for i, filename in enumerate(sorted(os.listdir(CARDS_FOLDER))):
        if filename.startswith('.'):
            continue
        
        filepath = os.path.join(CARDS_FOLDER, filename)
        if not os.path.isfile(filepath):
            continue
        
        character_key = extract_character_key_from_filename(filename)
        
        card_entry = {
            "name": character_key.title(),
            "filename": filename,
            "character_key": character_key,
            "file_id": None,  # Will be populated by sync_media_to_telegram
            "image_url": None,  # Will be populated by migrate_to_imgbb
        }
        cards.append(card_entry)
        logging.info(f"  Added: {filename} -> {character_key}")
    
    with open(CARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    
    logging.info(f"✅ Created {CARDS_FILE} with {len(cards)} entries")


def init_guides_json():
    """Create guides.json from local guides/ directory"""
    if os.path.isfile(GUIDES_FILE):
        logging.info(f"{GUIDES_FILE} already exists, skipping")
        return
    
    if not os.path.isdir(GUIDES_FOLDER):
        logging.warning(f"{GUIDES_FOLDER} directory not found")
        return
    
    guides = []
    for filename in sorted(os.listdir(GUIDES_FOLDER)):
        if filename.startswith('.'):
            continue
        
        filepath = os.path.join(GUIDES_FOLDER, filename)
        if not os.path.isfile(filepath):
            continue
        
        character_key = extract_character_key_from_filename(filename)
        
        guide_entry = {
            "name": character_key.title(),
            "filename": filename,
            "character_key": character_key,
            "file_id": None,  # Will be populated by sync_media_to_telegram
            "image_url": None,  # Will be populated by migrate_to_imgbb
        }
        guides.append(guide_entry)
        logging.info(f"  Added: {filename} -> {character_key}")
    
    with open(GUIDES_FILE, 'w', encoding='utf-8') as f:
        json.dump(guides, f, ensure_ascii=False, indent=2)
    
    logging.info(f"✅ Created {GUIDES_FILE} with {len(guides)} entries")


def main():
    """Initialize both JSON files"""
    logging.info("Initializing metadata files...")
    logging.info(f"Scanning {CARDS_FOLDER}...")
    init_cards_json()
    logging.info(f"Scanning {GUIDES_FOLDER}...")
    init_guides_json()
    logging.info("✅ Metadata initialization complete")


if __name__ == "__main__":
    main()
