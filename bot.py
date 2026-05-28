import os
import json
import logging
import asyncio
import re
import traceback
from dotenv import load_dotenv
from aiogram.types import InlineQuery,InlineQueryResultArticle,InputTextMessageContent

from aiogram import Bot, Router, Dispatcher, types

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

CARDS_FOLDER = "cards"
GUIDES_FOLDER = "guides"
ARTIFACTS_FOLDER = "artifacts"
ARTIFACTS_INFO_FILE = os.path.join(ARTIFACTS_FOLDER, "info.json")
ADMIN_IDS = {1675903713}
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID"))

ALIASES = {
    "yunjin": "yun jin",
    "heizou": "shikanoin heizou",
    "shinobu": "kuki shinobu",
    "kujousara": "kujou sara",
}

_artifact_info_cache = None
_character_file_cache = {}
_file_id_cache = {}
async def send_log(bot: Bot, text: str):
    try:
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


async def send_artifact_preview(
    message: types.Message,
    image_name: str,
    caption: str | None = None
):
    repo_raw_url = "https://raw.githubusercontent.com/HATheekshana/collei/main/artifacts"

    full_image_url = f"{repo_raw_url}/{image_name}"

    hidden_link = f'<a href="{full_image_url}">&#8203;</a>'

    text = hidden_link

    if caption:
        text += caption

    await message.reply(text, parse_mode="HTML")
async def send_cached_media_group(
    message: types.Message,
    files: list[str]
):
    global _file_id_cache

    media = []

    for path in files:

        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(path)[1].lower()

        is_image = ext in (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif"
        )

        try:
            # Use cached file_id
            if path in _file_id_cache:

                file_id = _file_id_cache[path]

                if is_image:
                    media.append(
                        types.InputMediaPhoto(
                            media=file_id
                        )
                    )
                else:
                    media.append(
                        types.InputMediaDocument(
                            media=file_id
                        )
                    )

            else:
                # Upload local file
                file = types.FSInputFile(path)

                if is_image:
                    media.append(
                        types.InputMediaPhoto(
                            media=file
                        )
                    )
                else:
                    media.append(
                        types.InputMediaDocument(
                            media=file
                        )
                    )

        except Exception:
            logging.exception(
                "Failed preparing media %s",
                path
            )

    if not media:
        return

    try:
        sent_messages = await message.answer_media_group(
            media,
            reply_parameters=types.ReplyParameters(
                message_id=message.message_id
            )
        )

        # Cache uploaded file_ids
        for path, sent in zip(files, sent_messages):

            try:
                if sent.photo:
                    _file_id_cache[path] = sent.photo[-1].file_id

                elif sent.document:
                    _file_id_cache[path] = sent.document.file_id

            except Exception:
                pass

    except Exception:

        error_text = traceback.format_exc()

        logging.exception("Media group failed")

        await send_log(
            message.bot,
            f"❌ Media group failed\n\n{error_text[:3500]}"
        )


router = Router()


@router.message()
async def handle_message(message: types.Message):
    # Handle commands
    if message.text and message.text.startswith("/"):
        command = message.text.split()[0][1:].split('@')[0].lower()
        user = message.from_user

        username = (
            f"@{user.username}"
            if user.username else
            "None"
        )

        await send_log(
            message.bot,
            f"📥 Command Used\n\n"
            f"👤 User: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📛 Username: {username}\n"
            f"💬 Command: /{command}"
        )
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
                await message.reply(artifact_caption, parse_mode="HTML")
            return

        character = ALIASES.get(command, command)
        files = find_character_files(character)

        if not files:
            await message.reply(f"No files found for {character.title()}.")
            return

        
        # Telegram allows max 10 media per album
        CHUNK_SIZE = 10

        for i in range(0, len(files), CHUNK_SIZE):

            chunk = files[i:i + CHUNK_SIZE]

            await send_cached_media_group(
                message,
                chunk
            )
@router.inline_query()
async def inline_search(inline_query: InlineQuery):

    query = inline_query.query.strip().lower()

    if not query:
        return

    character = ALIASES.get(query, query)

    files = find_character_files(character)

    results = []

    if files:

        results.append(
            InlineQueryResultArticle(
                id=character,
                title=character.title(),
                description=f"Send guides for {character.title()}",
                input_message_content=InputTextMessageContent(
                    message_text=f"/{query}"
                )
            )
        )

    await inline_query.answer(
        results=results,
        cache_time=1
    )

async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=TOKEN)

    dp = Dispatcher()
    dp.include_router(router)

    build_character_cache()

    logging.info("Bot started (aiogram v3)")
    await send_log(bot, "✅ Bot started successfully")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
