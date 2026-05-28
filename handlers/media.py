import os
import logging
import traceback
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

        await send_log(
            message.bot,
            f"❌ Media group failed\n\n{error_text[:3500]}"
        )
