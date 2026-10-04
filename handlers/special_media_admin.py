import logging

from aiogram import types

from data.config import ADMIN_IDS, MEDIA_CHANNEL
from utils.special_media import add_media, delete_all, get_media, LABELS

PHASE_LABELS = {"current": "Current", "next": "Next"}


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


# ---------------------------------------------------------------------------
# /addabyss  /addtheatre  /addstygian      -> current-phase images
# /addnextabyss  /addnexttheatre  /addnextstygian  -> next-phase images
# ---------------------------------------------------------------------------

async def _handle_add_special(message: types.Message, phase: str, category: str):
    """
    Usage: reply to a photo with /add<category> (current) or /addnext<category> (next)

    Adds ONE image per call — call it again (replying to another photo) to
    add more images to the same phase+category. Admin only.
    """
    label = LABELS.get(category, category.title())
    phase_label = PHASE_LABELS.get(phase, phase.title())
    command_name = f"add{category}" if phase == "current" else f"addnext{category}"

    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    replied = message.reply_to_message
    if not replied or not replied.photo:
        await message.reply(
            f"Please reply to a photo message with /{command_name}.\n"
            f"Note: send the image as a photo, not as a file/document.\n"
            f"You can run this multiple times to add more {phase_label} {label} images."
        )
        return

    photo = replied.photo[-1]
    status_msg = await message.reply(f"⏳ Uploading {phase_label} {label} image...")

    try:
        sent = await message.bot.send_photo(
            chat_id=MEDIA_CHANNEL,
            photo=photo.file_id,
            caption=f"{phase_label} {label} record image",
        )
        channel_file_id = sent.photo[-1].file_id
    except Exception:
        logging.exception("Failed to send %s %s image to channel", phase, category)
        await status_msg.edit_text(
            "Failed to send the image to the storage channel. "
            "Make sure the bot is an admin in that channel."
        )
        return

    # Try to upload to imgbb too (non-blocking) so this image can be shown as
    # a real preview link in inline mode, same as cards/guides.
    imgbb_url = None
    try:
        from utils.imgbb import upload_file_by_telegram_download, ImgBBUploadError
        try:
            imgbb_url = await upload_file_by_telegram_download(
                message.bot, photo.file_id,
                filename=f"{phase}_{category}_{photo.file_id[-8:]}.jpg",
            )
            logging.info("Successfully uploaded %s %s image to imgbb: %s", phase, category, imgbb_url)
        except ImgBBUploadError as e:
            logging.warning("imgbb upload failed (will use Telegram fallback): %s", e)
    except Exception as e:
        logging.warning("Error with imgbb upload: %s", e)

    if not add_media(phase, category, channel_file_id, image_url=imgbb_url):
        await status_msg.edit_text(
            f"Image sent to channel but failed to save to {phase_label} {label} records. Check logs."
        )
        return

    total = len(get_media(phase, category))
    imgbb_status = " ✨ (with inline preview)" if imgbb_url else " (Telegram storage only — no inline preview)"
    await status_msg.edit_text(
        f"✅ Image added for <b>{phase_label} {label}</b> ({total} total).{imgbb_status}",
        parse_mode="HTML",
    )
    logging.info(
        "%s %s image added, file_id=%s, imgbb=%s (total now %d)",
        phase, category, channel_file_id, imgbb_url or "none", total,
    )


# ---------------------------------------------------------------------------
# /delabyss  /deltheatre  /delstygian          -> current-phase images
# /delnextabyss  /delnexttheatre  /delnextstygian  -> next-phase images
# ---------------------------------------------------------------------------

async def _handle_del_special(message: types.Message, phase: str, category: str):
    """Usage: /del<category> or /delnext<category> — deletes ALL images stored for that phase+category. Admin only."""
    label = LABELS.get(category, category.title())
    phase_label = PHASE_LABELS.get(phase, phase.title())

    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    removed = delete_all(phase, category)
    if removed == 0:
        await message.reply(f"No images found for <b>{phase_label} {label}</b>.", parse_mode="HTML")
        return

    await message.reply(
        f"🗑 Deleted {removed} image(s) for <b>{phase_label} {label}</b>.",
        parse_mode="HTML",
    )
    logging.info("%s %s images deleted (%d entries removed)", phase, category, removed)


# ---------------------------------------------------------------------------
# Public entry points — current phase (/addabyss, /delabyss, ...)
# ---------------------------------------------------------------------------

async def handle_addabyss_command(message: types.Message):
    await _handle_add_special(message, "current", "abyss")


async def handle_addtheatre_command(message: types.Message):
    await _handle_add_special(message, "current", "theatre")


async def handle_addstygian_command(message: types.Message):
    await _handle_add_special(message, "current", "stygian")


async def handle_delabyss_command(message: types.Message):
    await _handle_del_special(message, "current", "abyss")


async def handle_deltheatre_command(message: types.Message):
    await _handle_del_special(message, "current", "theatre")


async def handle_delstygian_command(message: types.Message):
    await _handle_del_special(message, "current", "stygian")


# ---------------------------------------------------------------------------
# Public entry points — next phase (/addnextabyss, /delnextabyss, ...)
# ---------------------------------------------------------------------------

async def handle_addnextabyss_command(message: types.Message):
    await _handle_add_special(message, "next", "abyss")


async def handle_addnexttheatre_command(message: types.Message):
    await _handle_add_special(message, "next", "theatre")


async def handle_addnextstygian_command(message: types.Message):
    await _handle_add_special(message, "next", "stygian")


async def handle_delnextabyss_command(message: types.Message):
    await _handle_del_special(message, "next", "abyss")


async def handle_delnexttheatre_command(message: types.Message):
    await _handle_del_special(message, "next", "theatre")


async def handle_delnextstygian_command(message: types.Message):
    await _handle_del_special(message, "next", "stygian")
