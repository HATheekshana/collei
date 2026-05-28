
from data.config import ARTIFACTS_FOLDER, ARTIFACTS_INFO_FILE
from utils.helper import normalize_name
import json
import logging
import os
import re

_artifact_info_cache = None
def load_artifact_info() -> dict:
    global _artifact_info_cache
    if _artifact_info_cache is not None:
        return _artifact_info_cache

    if not os.path.isfile(ARTIFACTS_INFO_FILE):
        _artifact_info_cache = {}
        return _artifact_info_cache

    try:
        with open(ARTIFACTS_INFO_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        logging.exception("Failed to load artifact info")
        _artifact_info_cache = {}
        return _artifact_info_cache

    if isinstance(data, dict):
        entries = list(data.values())
    elif isinstance(data, list):
        entries = data
    else:
        entries = []

    info_map = {}
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        info_map[normalize_name(name)] = entry

    _artifact_info_cache = info_map
    return _artifact_info_cache


def find_artifact_info(artifact: str) -> dict | None:
    normalized_artifact = normalize_name(artifact)
    artifact_info = load_artifact_info()

    for normalized_name, entry in artifact_info.items():
        if normalized_name.startswith(normalized_artifact):
            return entry
    return None


def load_artifact_info_raw():
    if not os.path.isfile(ARTIFACTS_INFO_FILE):
        return []

    try:
        with open(ARTIFACTS_INFO_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        logging.exception("Failed to load raw artifact info")
        return []
def parse_artifact_payload(payload: str) -> tuple[str | None, dict]:
    pattern = re.compile(r"\b\d+-Piece(?:\s+Effect)?\s*:", re.IGNORECASE)
    match = pattern.search(payload)
    if match:
        name = payload[: match.start()].strip()
        rest = payload[match.start() :].strip()
    else:
        if ":" in payload:
            name, rest = payload.split(":", 1)
            name = name.strip()
            rest = rest.strip()
        else:
            return payload.strip() or None, {}

    def normalize_piece_key(raw_key: str) -> str:
        lower = raw_key.lower()
        if lower.startswith("2-piece"):
            return "2-Piece Effect"
        if lower.startswith("4-piece"):
            return "4-Piece Effect"
        return raw_key.strip()

    data = {}
    if rest:
        sections = re.split(r"(?=\b\d+-Piece(?:\s+Effect)?\s*:)", rest, flags=re.IGNORECASE)
        for section in sections:
            if not section.strip():
                continue
            if ":" not in section:
                continue
            key, value = section.split(":", 1)
            key = normalize_piece_key(key)
            value = value.strip()
            if key and value:
                data[key] = value

    return name or None, data


def save_artifact_info_entry(entry: dict) -> bool:
    artifact_name = entry.get("name") if isinstance(entry, dict) else None
    if not artifact_name:
        return False

    if not os.path.isdir(ARTIFACTS_FOLDER):
        os.makedirs(ARTIFACTS_FOLDER, exist_ok=True)

    raw_data = load_artifact_info_raw()
    normalized_name = normalize_name(artifact_name)

    if isinstance(raw_data, list):
        replaced = False
        for idx, existing in enumerate(raw_data):
            if isinstance(existing, dict) and normalize_name(existing.get("name", "")) == normalized_name:
                raw_data[idx] = entry
                replaced = True
                break
        if not replaced:
            raw_data.append(entry)
        save_data = raw_data
    elif isinstance(raw_data, dict):
        raw_data[normalized_name] = entry
        save_data = raw_data
    else:
        save_data = [entry]

    try:
        with open(ARTIFACTS_INFO_FILE, "w", encoding="utf-8") as fh:
            json.dump(save_data, fh, ensure_ascii=False, indent=2)
        global _artifact_info_cache
        _artifact_info_cache = None
        load_artifact_info()
        return True
    except Exception:
        logging.exception("Failed to save artifact info")
        return False
