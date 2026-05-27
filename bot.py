import os
import json
import logging
import asyncio
import time
import re
from aiogram import Bot, Router, Dispatcher, types

TOKEN = "8834632447:AAF5vqYp9N31Q8ANMk2tg0ukA8JOiu4R4tk"

CARDS_FOLDER = "cards"
GUIDES_FOLDER = "guides"
ARTIFACTS_FOLDER = "artifacts"
ARTIFACTS_INFO_FILE = os.path.join(ARTIFACTS_FOLDER, "info.json")
ADMIN_IDS = {1675903713}

ALIASES = {
    "yunjin": "yun jin",
    "heizou": "shikanoin heizou",
    "shinobu": "kuki shinobu",
    "kujousara": "kujou sara",
}

_artifact_info_cache = None

def normalize_name(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "").replace(" ", "")

def find_character_files(character: str) -> list:
    files = []
    normalized_character = (
        character.lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
    
    for folder in [GUIDES_FOLDER, CARDS_FOLDER]:
        if not os.path.isdir(folder):
            continue
        
        for fname in os.listdir(folder):
            # Remove extension before normalization
            name_without_ext = os.path.splitext(fname)[0]
            normalized_file = (
                name_without_ext.lower()
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "")
            )
            
            if normalized_file.startswith(normalized_character):
                files.append(os.path.join(folder, fname))
    
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


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


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

    data = {}
    if rest:
        sections = re.split(r"(?=\b\d+-Piece(?:\s+Effect)?\s*:)", rest, flags=re.IGNORECASE)
        for section in sections:
            if not section.strip():
                continue
            if ":" not in section:
                continue
            key, value = section.split(":", 1)
            key = key.strip()
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

    info_map = load_artifact_info()
    normalized_name = normalize_name(artifact_name)
    info_map[normalized_name] = entry

    try:
        with open(ARTIFACTS_INFO_FILE, "w", encoding="utf-8") as fh:
            json.dump(info_map, fh, ensure_ascii=False, indent=2)
        global _artifact_info_cache
        _artifact_info_cache = info_map
        return True
    except Exception:
        logging.exception("Failed to save artifact info")
        return False


async def handle_add_artifact_command(message: types.Message):
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    if not message.text:
        await message.reply("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    artifact_name, artifact_data = parse_artifact_payload(parts[1].strip())
    if not artifact_name:
        await message.reply(
            "Could not parse artifact name. Use /addarti Artifact Name 2-Piece: ... 4-Piece: ..."
        )
        return

    entry = {"name": artifact_name}
    entry.update(artifact_data)
    if not save_artifact_info_entry(entry):
        await message.reply("Failed to save artifact info. Check bot logs.")
        return

    saved_fields = ", ".join(artifact_data.keys()) or "details"
    await message.reply(f"Artifact info saved for {artifact_name} ({saved_fields}).")


async def send_artifact_preview(message: types.Message, image_name: str, caption: str | None = None):
    """Send a hidden-link preview to the raw GitHub artifact image to avoid caching issues.

    Uses a zero-width-space anchor so Telegram shows the image preview but hides the link text.
    """
    repo_raw_url = "https://raw.githubusercontent.com/HATheekshana/collei/main/artifacts"
    timestamp = int(time.time())
    full_image_url = f"{repo_raw_url}/{image_name}?v={timestamp}"
    hidden_link = f'<a href="{full_image_url}">&#8203;</a>'

    text = hidden_link
    if caption:
        text += caption

    await message.reply(text, parse_mode="HTML")


async def send_media(message: types.Message, media: list, caption: str | None = None):
    if not media:
        return
    if len(media) == 1:
        single = media[0]
        if isinstance(single, types.InputMediaPhoto):
            if caption:
                await message.answer_document(
                    document=single.media,
                    caption=caption,
                    parse_mode="HTML",
                )
            else:
                await message.answer_photo(
                    photo=single.media,
                    caption=caption,
                    parse_mode="HTML",
                )
        else:
            await message.answer_document(
                document=single.media,
                caption=caption,
                parse_mode="HTML",
            )
        return

    if caption and hasattr(media[0], "caption"):
        media[0].caption = caption
        media[0].parse_mode = "HTML"
    await message.reply_media_group(media)


router = Router()


@router.message()
async def handle_message(message: types.Message):
    # Handle commands
    if message.text and message.text.startswith("/"):
        command = message.text.split()[0][1:].split('@')[0].lower()

        if command == "start":
            await message.reply(
                "Welcome! Send a character command like /ganyu or /raiden to get their guides and material cards."
            )
            return

        if command == "addarti":
            await handle_add_artifact_command(message)
            return

        artifact_info = find_artifact_info(command)
        artifact_files = find_artifact_files(command)

        if artifact_info or artifact_files:
            artifact_caption = None
            if artifact_info:
                info_lines = [f"<b>Artifact:</b> {artifact_info.get('name', command.title())}\n\n"]
                for key in ["2-Piece Effect", "4-Piece Effect"]:
                    if key in artifact_info:
                        info_lines.append(f"<b>{key}</b>\n{artifact_info[key]}")
                artifact_caption = "\n\n".join(info_lines)

            if artifact_files:
                # Prefer sending remote previews from the GitHub artifacts folder
                # This uses a hidden zero-width-space link so Telegram shows the image preview
                for idx, path in enumerate(artifact_files):
                    try:
                        fname = os.path.basename(path)
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                            # fallback to sending the local file if it's not an image
                            if os.path.isfile(path):
                                await message.reply_document(types.FSInputFile(path))
                            continue

                        cap = artifact_caption if idx == 0 else None
                        await send_artifact_preview(message, fname, caption=cap)
                    except Exception:
                        logging.exception("Failed to send preview %s", path)

                artifact_caption = None

            if artifact_caption:
                await message.reply(artifact_caption)
            return

        character = ALIASES.get(command, command)
        files = find_character_files(character)

        if not files:
            await message.reply(f"No files found for {character.title()}.")
            return

        # Collect image files for media group
        media = []
        for path in files[:10]:  # Telegram limit: 10 media per group
            try:
                if not os.path.isfile(path):
                    logging.warning("Not a file: %s", path)
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    media.append(types.InputMediaPhoto(media=types.FSInputFile(path)))
                else:
                    media.append(types.InputMediaDocument(media=types.FSInputFile(path)))
            except Exception:
                logging.exception("Failed to process %s", path)

        # Send media group or single file if we have media
        if media:
            await send_media(message, media)

        # Send remaining files individually (if more than 10)
        for path in files[10:]:
            try:
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    await message.reply_photo(types.FSInputFile(path))
                else:
                    await message.reply_document(types.FSInputFile(path))
            except Exception:
                logging.exception("Failed to send %s", path)


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    logging.info("Bot started (aiogram v3)")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
