import os
import html
import logging
import traceback
import asyncio
from urllib.parse import quote
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from aiogram import Bot, types
from utils.helper import send_log

_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HATheekshana/collei/main"

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


def _github_raw_url(path: str) -> str:
    rel = path.replace("\\", "/").lstrip("./")
    if os.path.isabs(rel):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{_GITHUB_RAW_BASE}/{quote(rel, safe='/:')}"


def _supported_rich_media(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm")


def _rich_media_tag(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    url = _github_raw_url(path)
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return f'<img src="{url}"/>'
    return f'<video src="{url}"/>'


async def _raw_api_request(bot: Bot, method: str, payload: dict) -> dict:
    """Make a raw Telegram API request for unsupported methods like sendRichMessage."""
    session = getattr(bot, "session", None)
    if session is None:
        raise RuntimeError("Bot session not available for raw API request")

    client = await session.create_session()
    url = session.api.api_url(token=bot.token, method=method)

    async with client.post(url, json=payload, timeout=session.timeout) as resp:
        text = await resp.text()

    try:
        data = session.json_loads(text)
    except Exception as error:
        raise RuntimeError(
            f"Failed to decode {method} response: {error}\n{text}"
        ) from error

    if not data.get("ok", False):
        raise RuntimeError(
            f"{method} failed: {data.get('description', text)}"
        )

    return data["result"]


# ---------------------------------------------------------------------------
# Rich slideshow from already-uploaded Telegram file_ids
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rich slideshow from resolved media (imgBB URL preferred, Telegram file_id
# fallback) — each item is {"image_url": ...} or {"file_id": ...}
# ---------------------------------------------------------------------------

async def send_media_slideshow(
    message: types.Message,
    media_items: list[dict],
    caption: str | None = None,
) -> bool:
    """
    Send character cards/guides as a rich tg-slideshow when every item has a
    public imgBB URL. If any item only has a Telegram file_id (imgBB upload
    failed for it), fall back to a native Telegram media group instead,
    since file_ids cannot be embedded in rich message HTML.
    """
    if not media_items:
        return False

    logging.info(f"send_media_slideshow called with {len(media_items)} items: {media_items}")

    urls = [m["image_url"] for m in media_items if m.get("image_url")]
    has_file_id_only = any("image_url" not in m and m.get("file_id") for m in media_items)

    logging.info(f"URLs found: {len(urls)}, has_file_id_only: {has_file_id_only}, total items: {len(media_items)}")

    # Only attempt the rich slideshow if every item resolved to a public URL.
    if urls and not has_file_id_only and len(urls) == len(media_items):
        blocks = [f'<img src="{u}"/>' for u in urls]
        slideshow = "<tg-slideshow>" + "".join(blocks)
        if caption:
            slideshow += f"<figcaption>{html.escape(caption)}</figcaption>"
        slideshow += "</tg-slideshow>"

        logging.info(f"Attempting rich slideshow with {len(urls)} images")
        api_kwargs: dict = {
            "chat_id": message.chat.id,
            "rich_message": {"html": slideshow},
        }
        if message.message_thread_id:
            api_kwargs["message_thread_id"] = message.message_thread_id
        api_kwargs["reply_parameters"] = {"message_id": message.message_id}

        try:
            await _raw_api_request(message.bot, "sendRichMessage", api_kwargs)
            logging.info("Rich slideshow sent successfully")
            return True
        except Exception as e:
            err = str(e)
            logging.warning(f"Rich slideshow failed: {err}")
            if "message to be replied not found" in err:
                api_kwargs.pop("reply_parameters", None)
                try:
                    await _raw_api_request(message.bot, "sendRichMessage", api_kwargs)
                    logging.info("Rich slideshow sent successfully (without reply ref)")
                    return True
                except Exception as e2:
                    err = str(e2)
                    logging.warning(f"Rich slideshow retry failed: {err}")
            logging.warning("Rich slideshow (imgBB URLs) failed (%s), falling back to media group", err)

    # Fallback: native Telegram media group, mixing URLs and file_ids freely
    # (Telegram's InputMediaPhoto accepts either a URL string or a file_id).
    logging.info("Falling back to media group")
    await _send_mixed_media_group(message, media_items, caption=caption)
    return True


async def _send_mixed_media_group(
    message: types.Message,
    media_items: list[dict],
    caption: str | None = None,
):
    """answer_media_group fallback accepting imgBB URLs or Telegram file_ids."""
    sources = [m.get("image_url") or m.get("file_id") for m in media_items]
    sources = [s for s in sources if s]

    CHUNK = 10
    for i in range(0, len(sources), CHUNK):
        chunk = sources[i:i + CHUNK]
        media = []
        for idx, src in enumerate(chunk):
            if idx == 0 and i == 0 and caption:
                media.append(types.InputMediaPhoto(media=src, caption=caption, parse_mode="HTML"))
            else:
                media.append(types.InputMediaPhoto(media=src))
        try:
            try:
                await message.answer_media_group(
                    media,
                    reply_parameters=types.ReplyParameters(message_id=message.message_id),
                )
            except TelegramBadRequest as e:
                if "message to be replied not found" in str(e):
                    await message.answer_media_group(media)
                else:
                    raise
        except Exception:
            logging.exception("Mixed media group fallback failed for chunk starting at %d", i)


# Backwards-compat shim: older call sites may still pass a flat list of
# file_ids. Wrap them as {"file_id": ...} dicts and delegate.
async def send_rich_slideshow_from_file_ids(
    message: types.Message,
    file_ids: list[str],
    caption: str | None = None,
) -> bool:
    media_items = [{"file_id": fid} for fid in file_ids]
    return await send_media_slideshow(message, media_items, caption=caption)


# ---------------------------------------------------------------------------
# Rich slideshow from local file paths (used for artifacts still on disk)
# ---------------------------------------------------------------------------

async def send_rich_slideshow(
    message: types.Message,
    files: list[str],
    caption: str | None = None,
) -> bool:
    blocks = []
    for path in files:
        if not os.path.isfile(path):
            continue
        if not _supported_rich_media(path):
            continue
        blocks.append(_rich_media_tag(path))

    if not blocks:
        return False

    slideshow = "<tg-slideshow>" + "".join(blocks)
    if caption:
        slideshow += f"<figcaption>{html.escape(caption)}</figcaption>"
    slideshow += "</tg-slideshow>"

    api_kwargs = {
        "chat_id": message.chat.id,
        "rich_message": {"html": slideshow},
    }
    if message.message_thread_id:
        api_kwargs["message_thread_id"] = message.message_thread_id
    api_kwargs["reply_parameters"] = {"message_id": message.message_id}

    try:
        await _raw_api_request(message.bot, "sendRichMessage", api_kwargs)
        return True
    except Exception as e:
        err = str(e)
        if "message to be replied not found" in err:
            logging.warning("Reply message gone, retrying rich slideshow without reply ref")
            api_kwargs.pop("reply_parameters", None)
            try:
                await _raw_api_request(message.bot, "sendRichMessage", api_kwargs)
                return True
            except Exception as e2:
                err = str(e2)
        if "RICH_MESSAGE_PHOTO_NO_MEDIA_FOUND" in err or "Bad Request" in err:
            logging.warning("Rich slideshow failed (%s), falling back to media group upload", err)
            await send_cached_media_group(message, files, caption=caption)
            return True
        raise


# ---------------------------------------------------------------------------
# send_cached_media_group — local file upload with in-memory file_id cache
# ---------------------------------------------------------------------------

async def send_cached_media_group(
    message: types.Message,
    files: list[str],
    caption: str | None = None
):
    global _file_id_cache

    media = []
    first_added = False

    for path in files:
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        is_image = ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")

        try:
            media_source = _file_id_cache[path] if path in _file_id_cache else types.FSInputFile(path)

            if is_image:
                if caption and not first_added:
                    item = types.InputMediaPhoto(media=media_source, caption=caption, parse_mode="HTML")
                    first_added = True
                else:
                    item = types.InputMediaPhoto(media=media_source)
            else:
                item = types.InputMediaDocument(media=media_source)

            media.append(item)
        except Exception:
            logging.exception("Failed preparing media %s", path)

    if not media:
        return

    try:
        try:
            sent_messages = await message.answer_media_group(
                media,
                reply_parameters=types.ReplyParameters(message_id=message.message_id)
            )
        except TelegramBadRequest as e:
            if "message to be replied not found" in str(e):
                logging.warning("Reply message gone, sending media group without reply ref")
                sent_messages = await message.answer_media_group(media)
            else:
                raise

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

        for path in files:
            try:
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                is_image = ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")

                if path in _file_id_cache:
                    fid = _file_id_cache[path]
                    if is_image:
                        try:
                            sent = await message.reply_photo(fid)
                        except TelegramBadRequest:
                            sent = await message.answer_photo(fid)
                        if sent.photo:
                            _file_id_cache[path] = sent.photo[-1].file_id
                    else:
                        try:
                            sent = await message.reply_document(fid)
                        except TelegramBadRequest:
                            sent = await message.answer_document(fid)
                        if sent.document:
                            _file_id_cache[path] = sent.document.file_id
                else:
                    if is_image:
                        try:
                            sent = await message.reply_photo(types.FSInputFile(path))
                        except TelegramBadRequest:
                            sent = await message.answer_photo(types.FSInputFile(path))
                        if sent.photo:
                            _file_id_cache[path] = sent.photo[-1].file_id
                    else:
                        try:
                            sent = await message.reply_document(types.FSInputFile(path))
                        except TelegramBadRequest:
                            sent = await message.answer_document(types.FSInputFile(path))
                        if sent.document:
                            _file_id_cache[path] = sent.document.file_id

                await asyncio.sleep(0.25)

            except TelegramNetworkError:
                logging.exception("Network error while sending %s", path)
                await asyncio.sleep(1)
            except Exception:
                logging.exception("Failed sending fallback media %s", path)

        await send_log(
            message.bot,
            f"❌ Media group failed\n\n{error_text[:3500]}"
        )