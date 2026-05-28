import os
import logging
import traceback
import asyncio
from aiogram.exceptions import TelegramNetworkError
from aiogram import types
from utils.helper import send_log

_file_id_cache = {}
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

        # Fallback: send files individually (more resilient to timeouts)
        for path in files:
            try:
                if not os.path.isfile(path):
                    continue

                ext = os.path.splitext(path)[1].lower()
                is_image = ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")

                # Use cached file_id if available
                if path in _file_id_cache:
                    fid = _file_id_cache[path]
                    if is_image:
                        sent = await message.reply_photo(fid)
                        if sent.photo:
                            _file_id_cache[path] = sent.photo[-1].file_id
                    else:
                        sent = await message.reply_document(fid)
                        if sent.document:
                            _file_id_cache[path] = sent.document.file_id
                else:
                    # Upload local file individually
                    if is_image:
                        sent = await message.reply_photo(types.FSInputFile(path))
                        if sent.photo:
                            _file_id_cache[path] = sent.photo[-1].file_id
                    else:
                        sent = await message.reply_document(types.FSInputFile(path))
                        if sent.document:
                            _file_id_cache[path] = sent.document.file_id

                # small delay to reduce pressure on network / Telegram
                await asyncio.sleep(0.25)

            except TelegramNetworkError:
                logging.exception("Network error while sending individual media %s", path)
                await asyncio.sleep(1)
            except Exception:
                logging.exception("Failed sending fallback media %s", path)

        await send_log(
            message.bot,
            f"❌ Media group failed\n\n{error_text[:3500]}"
        )
