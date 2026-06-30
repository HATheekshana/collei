import logging

from aiogram import types

from data.config import ADMIN_IDS
from utils.bosses import find_boss, set_boss_file_id

# The channel where boss images are stored so we get a permanent file_id
BOSS_IMAGE_CHANNEL = -1004339480119


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


async def handle_bossimg_command(message: types.Message):
    """
    Usage: reply to a photo with  /bossimg <boss name>

    Flow:
    1. Validate admin + replied photo.
    2. Forward the photo to BOSS_IMAGE_CHANNEL to get a stable file_id.
    3. Save that file_id to bosses.json under the given boss name.
    4. Confirm to the admin.
    """
    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    # Parse boss name from command args
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            "Usage: reply to a boss image with /bossimg <boss name>\n"
            "Example: /bossimg Stormterror Dvalin"
        )
        return

    boss_name_arg = parts[1].strip()

    # Must be a reply to a message that has a photo
    replied = message.reply_to_message
    if not replied or not replied.photo:
        await message.reply(
            "Please reply to a photo message with /bossimg <boss name>."
        )
        return

    # Check boss exists in bosses.json
    boss = find_boss(boss_name_arg)
    if not boss:
        await message.reply(
            f'Boss "{boss_name_arg}" not found in bosses.json.\n'
            f"Check the name and try again."
        )
        return

    # Use the largest available photo size
    photo = replied.photo[-1]

    try:
        # Send to storage channel to get a stable file_id
        sent = await message.bot.send_photo(
            chat_id=BOSS_IMAGE_CHANNEL,
            photo=photo.file_id,
            caption=f"Boss image: {boss['name']}",
        )
    except Exception:
        logging.exception("Failed to send boss image to channel")
        await message.reply(
            "Failed to send the image to the storage channel. "
            "Make sure the bot is an admin in that channel."
        )
        return

    # Extract the file_id from the channel message
    channel_file_id = sent.photo[-1].file_id

    # Persist to bosses.json
    if not set_boss_file_id(boss["name"], channel_file_id):
        await message.reply("Image sent to channel but failed to save file_id. Check logs.")
        return

    await message.reply(
        f'✅ Boss image saved for <b>{boss["name"]}</b>.\n'
        f"Users can now see it in /search and inline search.",
        parse_mode="HTML",
    )
    logging.info("Boss image saved: %s → %s", boss["name"], channel_file_id)