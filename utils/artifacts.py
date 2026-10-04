"""Artifact details are stored only in MongoDB; cached in memory for lookups."""
import logging
import re
from utils.helper import normalize_name

_artifact_info_cache = None

def load_artifact_info():
    if _artifact_info_cache is None:
        raise RuntimeError("Artifact database has not loaded. Use /artifactreload.")
    return _artifact_info_cache

def find_artifact_info(artifact: str) -> dict | None:
    normalized_artifact = normalize_name(artifact)
    artifact_info = load_artifact_info()

    for normalized_name, entry in artifact_info.items():
        if normalized_name.startswith(normalized_artifact):
            return entry
    return None


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


def save_artifact_info_entry(entry):
    from utils import artifact_db
    from data.search_items import SEARCH_ITEMS
    if not isinstance(entry, dict) or not entry.get("name"):
        return False
    try:
        saved = artifact_db.save(entry)
    except Exception as error:
        logging.error("Artifact database save failed: %s", type(error).__name__)
        return False
    key = normalize_name(saved["name"])
    if _artifact_info_cache is not None:
        _artifact_info_cache[key] = saved
    SEARCH_ITEMS[key] = saved["name"]
    return True
