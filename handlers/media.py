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
    character_key: str | None = None,
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

    unique=[]
    seen_ids=set();seen_urls=set()
    for item in media_items:
        fid=item.get("file_id");url=item.get("image_url")
        if (fid and fid in seen_ids) or (url and url in seen_urls):continue
        if fid:seen_ids.add(fid)
        if url:seen_urls.add(url)
        if fid or url:unique.append(item)
    media_items=unique
    attachments=[];blocks=[]
    for index,item in enumerate(media_items):
        identity=f"card_{index}"
        source=item.get("file_id") or item.get("image_url")
        attachments.append({"id":identity,"media":{"type":"photo","media":source}})
        blocks.append(f'<img src="tg://photo?id={identity}"/>')
    if blocks:
        slideshow = "<tg-slideshow>" + "".join(blocks)
        if caption:
            slideshow += f"<figcaption>{html.escape(caption)}</figcaption>"
        slideshow += "</tg-slideshow>"
        if character_key:
            slideshow += "<p>If a character card is unavailable, use /complain@collei_help_bot to report it.</p>"

        logging.info("Attempting rich slideshow with %d attached images",len(attachments))
        api_kwargs: dict = {
            "chat_id": message.chat.id,
            "rich_message": {"html": slideshow, "media": attachments},
        }
        if character_key:
            from utils.character_details import remember,keyboard
            origin=message.reply_to_message if message.from_user and message.from_user.is_bot else message
            owner=origin.from_user.id if origin and origin.from_user else 0
            token=remember(character_key,slideshow,owner,media=attachments)
            if token:api_kwargs["reply_markup"]=keyboard(token)
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
    fallback_caption = ((caption or "") + "\n\nIf a character card is unavailable, use /complain@collei_help_bot to report it.") if character_key else caption
    delivered = await _send_mixed_media_group(message, media_items, caption=fallback_caption)
    if not delivered:
        await message.reply("Could not send the saved card images. Please try again or ask an admin to check the media links.")
        return False
    if character_key:
        from utils.character_details import remember,keyboard
        original="<p>"+html.escape(caption or character_key)+" — cards are shown above.</p>"
        origin=message.reply_to_message if message.from_user and message.from_user.is_bot else message
        owner=origin.from_user.id if origin and origin.from_user else 0
        token=remember(character_key,original,owner)
        if token:
            await _raw_api_request(message.bot,"sendRichMessage",{
                "chat_id":message.chat.id,"rich_message":{"html":original},"reply_markup":keyboard(token),
                "reply_parameters":{"message_id":message.message_id}})
    return True


async def _send_mixed_media_group(
    message: types.Message,
    media_items: list[dict],
    caption: str | None = None,
):
    """Use native photos for singletons; report success only after delivery."""
    sources = [m.get("file_id") or m.get("image_url") for m in media_items]
    sources = [source for source in sources if source]
    if not sources:
        return False
    for i in range(0, len(sources), 10):
        chunk = sources[i:i + 10]
        async def send(reply=True):
            kwargs = {"reply_parameters": types.ReplyParameters(message_id=message.message_id)} if reply else {}
            if len(chunk) == 1:
                return await message.answer_photo(chunk[0], caption=caption if i==0 else None,
                                                  parse_mode=None, **kwargs)
            media = [types.InputMediaPhoto(media=src, caption=caption if i==0 and idx==0 else None,
                                           parse_mode=None) for idx,src in enumerate(chunk)]
            return await message.answer_media_group(media, **kwargs)
        try:
            try:
                await send()
            except TelegramBadRequest as error:
                if "message to be replied not found" in str(error).lower():
                    await send(reply=False)
                else:
                    raise
        except Exception:
            logging.exception("Card image delivery failed at chunk %d",i)
            return False
    return True


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