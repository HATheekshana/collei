import asyncio
import logging
import re

from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from data.config import ADMIN_IDS, LOG_CHAT_ID
from utils.broadcast_targets import (
    get_all_user_ids,
    get_all_group_ids,
    get_target_counts,
    remove_group,
    remove_user,
)


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


def content_html(message):
    """Parse typed HTML, while preserving Telegram formatting when no tags were typed."""
    raw = message.text or message.caption or ""
    if re.search(r"</?[a-zA-Z][^>]*>", raw):
        return raw
    # aiogram html_text formats both text/entities and caption/caption_entities.
    return message.html_text or ""


def prepare(message, rich):
    replied = message.reply_to_message
    parts = (message.text or "").split(maxsplit=1)
    body = content_html(replied) if replied else (parts[1] if len(parts) > 1 else "")
    # Command arguments can append button rows to a replied caption.
    if replied and len(parts) > 1:
        body += "\n" + parts[1]
    rows = []
    kept = []
    for line in body.splitlines():
        if line.startswith("BUTTONS:"):
            row = []
            for item in line[len("BUTTONS:"):].split(" | "):
                label, separator, url = item.partition(" => ")
                if not separator or not label.strip() or not url.strip().startswith(("https://", "http://", "tg://")):
                    raise ValueError("Use BUTTONS: Label => https://example.com | Label => https://example.com")
                row.append(types.InlineKeyboardButton(text=label.strip(), url=url.strip()))
            if len(row) > 8:
                raise ValueError("Use at most 8 buttons per row.")
            rows.append(row)
        else:
            kept.append(line)
    body = "\n".join(kept).strip()
    markup = types.InlineKeyboardMarkup(inline_keyboard=rows) if rows else (getattr(replied, "reply_markup", None) if replied else None)
    payload = {"reply_markup": markup} if markup else {}
    if rich:
        rich_message = {"html": body}
        if replied and replied.photo:
            rich_message["html"] = '<img src="tg://photo?id=broadcast_photo"/>' + body
            rich_message["media"] = [{"id": "broadcast_photo", "media": {"type": "photo", "media": replied.photo[-1].file_id}}]
        elif replied and not replied.text:
            raise ValueError("Rich broadcast currently accepts text or a replied photo with caption.")
        if not rich_message["html"]:
            raise ValueError("Add announcement text or reply to a photo.")
        return "send_rich_message", {**payload, "rich_message": rich_message}
    if replied and not replied.text:
        payload.update(from_chat_id=replied.chat.id, message_id=replied.message_id)
        if body:
            payload.update(caption=body, parse_mode="HTML")
        return "copy_message", payload
    if not body:
        raise ValueError("Add announcement text or reply to a message.")
    return "send_message", {**payload, "text": body, "parse_mode": "HTML"}


async def _send_one(bot, chat_id, prepared):
    method, payload = prepared
    await getattr(bot, method)(chat_id=chat_id, **payload)


async def handle_broadcast_command(message: types.Message):
    """Admin broadcasts and log-only previews. A reply selects one message, not its album."""
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    command = (message.text or "").split()[0].split("@")[0].lower()
    test = command in ("/tbroadcast", "/trbroadcast")
    rich = command in ("/rbroadcast", "/trbroadcast")
    if test and not LOG_CHAT_ID:
        await message.reply("Set LOG_CHAT_ID before using test broadcasts.")
        return
    try:
        prepared = prepare(message, rich)
    except ValueError as error:
        await message.reply(str(error) + "\nUse /broadcast or /rbroadcast to send; /tbroadcast or /trbroadcast to test in the log group.", parse_mode=None)
        return
    if test:
        targets = [(LOG_CHAT_ID, "test")]
    else:
        targets = list(dict.fromkeys(
            [(uid, "user") for uid in get_all_user_ids()] +
            [(gid, "group") for gid in get_all_group_ids()]
        ))

    if not targets:
        await message.reply(
            "No saved users or groups yet — /broadcast will start reaching "
            "people once they use the bot."
        )
        return

    status_msg = await message.reply(
        "Testing in the log group only..." if test else f"📢 Broadcasting to {len(targets)} chats..."
    )

    sent = 0
    failed = 0
    dead_users = []
    dead_groups = []

    for chat_id, kind in targets:
        try:
            await _send_one(message.bot, chat_id, prepared)
            sent += 1
        except TelegramRetryAfter as e:
            # Telegram is asking us to slow down — wait it out, then retry once.
            await asyncio.sleep(e.retry_after)
            try:
                await _send_one(message.bot, chat_id, prepared)
                sent += 1
            except Exception:
                logging.exception("Broadcast retry failed for %s %s", kind, chat_id)
                failed += 1
        except TelegramForbiddenError:
            # User blocked the bot, or the bot was removed from the group.
            failed += 1
            if kind == "user":
                dead_users.append(chat_id)
            elif kind == "group":
                dead_groups.append(chat_id)
        except TelegramBadRequest as error:
            failed += 1
            if test:
                await status_msg.edit_text(f"Test failed: {error.message}", parse_mode=None)
                return
        except Exception:
            logging.exception("Broadcast failed for %s %s", kind, chat_id)
            failed += 1

        await asyncio.sleep(0.05)  # stay well under Telegram's rate limits

    # Prune dead entries so future broadcasts don't keep retrying them.
    for uid in dead_users:
        remove_user(uid)
    for gid in dead_groups:
        remove_group(gid)

    result_lines = [
        "✅ Test finished (log group only)." if test else "✅ Broadcast finished.",
        f"Sent: {sent}",
        f"Failed: {failed}",
    ]
    if dead_users:
        result_lines.append(f"Removed {len(dead_users)} user(s) who blocked the bot.")
    if dead_groups:
        result_lines.append(f"Removed {len(dead_groups)} group(s) the bot is no longer in.")

    try:
        await status_msg.edit_text("\n".join(result_lines))
    except Exception:
        await message.reply("\n".join(result_lines))