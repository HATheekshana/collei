import logging
import os
from telegram import Bot
from data.config import LOG_CHAT_ID
from data.config import ARTIFACTS_FOLDER, ARTIFACTS_INFO_FILE, GUIDES_FOLDER, CARDS_FOLDER
_character_file_cache = {}


async def send_log(bot: Bot, text: str):
    try:
        if not LOG_CHAT_ID:
            logging.info("LOG_CHAT_ID not set; skipping send_log")
            return

        await bot.send_message(
            chat_id=LOG_CHAT_ID,
            text=text
        )
    except Exception:
        logging.exception("Failed to send log message")


def normalize_name(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "").replace(" ", "")
def build_character_cache():
    global _character_file_cache

    _character_file_cache = {}

    for folder in [GUIDES_FOLDER, CARDS_FOLDER]:
        if not os.path.isdir(folder):
            continue

        for fname in os.listdir(folder):
            path = os.path.join(folder, fname)

            name_without_ext = os.path.splitext(fname)[0]
            normalized = normalize_name(name_without_ext)

            if normalized not in _character_file_cache:
                _character_file_cache[normalized] = []

            _character_file_cache[normalized].append(path)
def find_character_files(character: str) -> list:
    global _character_file_cache

    if not _character_file_cache:
        build_character_cache()

    normalized_character = normalize_name(character)

    files = []

    for normalized_name, paths in _character_file_cache.items():
        if normalized_name.startswith(normalized_character):
            files.extend(paths)

    return sorted(files)


def find_artifact_files(artifact: str) -> list:
    files = []
    normalized_artifact = normalize_name(artifact)

    if not os.path.isdir(ARTIFACTS_FOLDER):
        return files

    for fname in os.listdir(ARTIFACTS_FOLDER):
        if fname == os.path.basename(ARTIFACTS_INFO_FILE):
            continue

        name_without_ext = os.path.splitext(fname)[0]
        normalized_file = normalize_name(name_without_ext)

        if normalized_file.startswith(normalized_artifact):
            files.append(os.path.join(ARTIFACTS_FOLDER, fname))

    return sorted(files)