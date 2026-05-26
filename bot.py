import os
import logging
import asyncio
from aiogram import Bot, Router, Dispatcher, types

TOKEN = "8834632447:AAF5vqYp9N31Q8ANMk2tg0ukA8JOiu4R4tk"

CARDS_FOLDER = "cards"
GUIDES_FOLDER = "guides"

ALIASES = {
    "yunjin": "yun jin",
    "heizou": "shikanoin heizou",
    "shinobu": "kuki shinobu",
    "kujousara": "kujou sara",
}

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


router = Router()


@router.message()
async def handle_message(message: types.Message):
    # Handle commands
    if message.text and message.text.startswith("/"):
        command = message.text.split()[0][1:].split('@')[0].lower()
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

        # Send media group if we have media
        if media:
            await message.reply_media_group(media)

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
