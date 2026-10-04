import asyncio
import logging
from aiogram import types
from utils.artifacts import parse_artifact_payload, save_artifact_info_entry
from utils.helper import normalize_name
from handlers.card_guide_admin import _resolve_character_key, _add_to_search_items
from data.config import ADMIN_IDS, MEDIA_CHANNEL, ADMIN_PANEL_URL
from data.search_items import SEARCH_ITEMS
from utils.banned_users import ban_user, unban_user
import os

def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


def _target_user_id(message: types.Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2:
        try:
            return int(parts[1].strip())
        except ValueError:
            return None
    return None


async def handle_ban_command(message: types.Message):
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    user_id = _target_user_id(message)
    if user_id is None:
        await message.reply("Usage: /ban <user_id> or reply to a user's message with /ban")
        return
    if user_id in ADMIN_IDS:
        await message.reply("Configured admins cannot be banned.")
        return
    if ban_user(user_id):
        await message.reply(f"User {user_id} has been banned.")
    else:
        await message.reply(f"User {user_id} is already banned.")


async def handle_unban_command(message: types.Message):
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    user_id = _target_user_id(message)
    if user_id is None:
        await message.reply("Usage: /unban <user_id> or reply to a user's message with /unban")
        return
    if unban_user(user_id):
        await message.reply(f"User {user_id} has been unbanned.")
    else:
        await message.reply(f"User {user_id} is not banned.")


def _get_replied_image(message: types.Message):
    """
    Return a (file_id, is_png_document) tuple for an image attached to the
    replied-to message, or (None, False) if there isn't one.

    Accepts either a compressed Telegram photo, or a document/file whose
    filename or mime type marks it as a PNG (so admins can reply with a
    raw, uncompressed .png without Telegram's photo compression).
    """
    replied = message.reply_to_message
    if not replied:
        return None, False

    if replied.photo:
        return replied.photo[-1].file_id, False

    doc = replied.document
    if doc:
        name = (doc.file_name or "").lower()
        mime = (doc.mime_type or "").lower()
        if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) or mime.startswith("image/"):
            return doc.file_id, True

    return None, False


async def handle_admin_panel_command(message: types.Message) -> None:
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    if message.chat.type != "private":
        await message.reply("Open this in a private chat with me — Telegram only allows Mini App buttons there.")
        return

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(
                text="Open Admin Panel",
                web_app=types.WebAppInfo(url=ADMIN_PANEL_URL),
            )
        ]]
    )
    await message.reply(
        "Tap below to open the admin panel. It signs you in automatically "
        "using this Telegram account — no separate login needed.",
        reply_markup=keyboard,
    )


async def handle_add_artifact_command(message: types.Message):
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    if not message.text:
        await message.reply("Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "Usage: /addarti Artifact Name 2-Piece: ... 4-Piece: ...\n"
            "Tip: reply to a PNG/photo of the artifact set with this command "
            "to save the image and the text together."
        )
        return

    artifact_name, artifact_data = parse_artifact_payload(parts[1].strip())
    if not artifact_name:
        await message.reply(
            "Could not parse artifact name. Use /addarti Artifact Name 2-Piece: ... 4-Piece: ..."
        )
        return

    entry = {"name": artifact_name}
    entry.update(artifact_data)

    search_key_notice = ""

    file_id, is_document = _get_replied_image(message)
    status_msg = None

    if file_id:
        status_msg = await message.reply(f"⏳ Uploading artifact image for {artifact_name}...")

        # Backup upload to the media channel so we always retain a Telegram
        # file_id we can resend instantly, regardless of imgbb availability.
        try:
            if is_document:
                sent = await message.bot.send_document(
                    chat_id=MEDIA_CHANNEL,
                    document=file_id,
                    caption=f"Artifact: {artifact_name}",
                )
                channel_file_id = sent.document.file_id
            else:
                sent = await message.bot.send_photo(
                    chat_id=MEDIA_CHANNEL,
                    photo=file_id,
                    caption=f"Artifact: {artifact_name}",
                )
                channel_file_id = sent.photo[-1].file_id
            entry["file_id"] = channel_file_id
        except Exception:
            logging.exception("Failed to send artifact image to channel")
            entry["file_id"] = file_id  # fall back to the original file_id

        # Upload to imgbb for a stable public URL usable in inline previews.
        try:
            from utils.imgbb import upload_file_by_telegram_download, ImgBBUploadError
            try:
                imgbb_url = await upload_file_by_telegram_download(
                    message.bot, file_id,
                    filename=f"{artifact_name}_{file_id[-8:]}.png",
                )
                entry["image_url"] = imgbb_url
            except ImgBBUploadError as e:
                logging.warning(f"imgbb upload failed for artifact {artifact_name}: {e}")
        except Exception as e:
            logging.warning(f"Error with imgbb upload for artifact {artifact_name}: {e}")

    if not await asyncio.to_thread(save_artifact_info_entry, entry):
        msg = "Failed to save artifact info. Check bot logs."
        if status_msg:
            await status_msg.edit_text(msg)
        else:
            await message.reply(msg)
        return

    saved_fields = ", ".join(artifact_data.keys()) or "details"
    image_status = ""
    if file_id:
        image_status = " ✨ (with imgbb link)" if entry.get("image_url") else " (Telegram storage only)"
    result_text = f"✅ Artifact info saved for {artifact_name} ({saved_fields}).{image_status}{search_key_notice}"

    if status_msg:
        await status_msg.edit_text(result_text)
    else:
        await message.reply(result_text)


async def handle_update_allcommands_command(message: types.Message):
    """Admin command: regenerate the allcommands list file from SEARCH_ITEMS."""
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    from utils import artifact_db
    await artifact_db.reload()
    from utils import weapon_db, character_media_db
    await weapon_db.reload()
    await character_media_db.reload()
    await message.reply(f"Commands refreshed from MongoDB ({len(SEARCH_ITEMS)} search entries).")
