import html
import logging

from aiogram import types
from aiogram.exceptions import TelegramBadRequest

from data.config import ADMIN_IDS, SUPPORT_CHAT_ID
from utils.complaints import record_complaint, get_complaint


def _user_label(user: types.User | None) -> str:
    if not user:
        return "Unknown"
    label = html.escape(user.full_name or "Unknown")
    if user.username:
        label += f" (@{html.escape(user.username)})"
    return label


async def handle_complain_command(message: types.Message):
    """
    /complain [text]              -> sends [text] to the support chat.
    Reply to a message (text, photo, video, document, etc.) with
    /complain [text]              -> forwards that message to the support
                                      chat together with the complaint text.
    """
    if not SUPPORT_CHAT_ID:
        await message.reply("Support chat isn't configured yet. Please try again later.")
        return

    user = message.from_user
    if not user:
        return

    complaint_text = message.text.partition(" ")[2].strip()
    replied = message.reply_to_message

    if not complaint_text and not replied:
        await message.reply(
            "Usage: /complain [your message]\n"
            "You can also reply to a message (text, photo, video, document, etc.) "
            "with /complain [your message] to send it to support."
        )
        return

    chat_label = (
        "Private chat" if message.chat.type == "private"
        else f"{html.escape(message.chat.title or 'Group')} ({message.chat.type})"
    )

    header_lines = [
        "📩 <b>New complaint</b>",
        f"From: {_user_label(user)}",
        f"User ID: <code>{user.id}</code>",
        f"Chat: {chat_label}",
    ]

    if complaint_text:
        header_lines.append("")
        header_lines.append(f"<b>Message:</b>\n{html.escape(complaint_text)}")

    if replied and replied.content_type == "text" and replied.text:
        header_lines.append("")
        header_lines.append(f"<b>Replied message:</b>\n{html.escape(replied.text)}")

    header = "\n".join(header_lines)

    try:
        header_msg = await message.bot.send_message(
            chat_id=SUPPORT_CHAT_ID, text=header, parse_mode="HTML"
        )

        # If the user replied to media (photo, video, document, sticker, etc.)
        # forward that media too, linked underneath the header message.
        if replied and replied.content_type != "text":
            try:
                await replied.copy_to(
                    chat_id=SUPPORT_CHAT_ID,
                    reply_parameters=types.ReplyParameters(message_id=header_msg.message_id),
                )
            except TelegramBadRequest:
                logging.exception("Failed to copy replied media to support chat")
    except Exception:
        logging.exception("Failed to forward complaint to support chat")
        await message.reply("Failed to send your complaint. Please try again later.")
        return

    record_complaint(
        header_msg.message_id,
        {
            "user_id": user.id,
            "user_name": user.full_name or "",
            "username": user.username or "",
            "chat_id": message.chat.id,
            "chat_type": message.chat.type,
            "text": complaint_text or "(see attached message)",
        },
    )

    await message.reply("✅ Your complaint has been sent to support. We'll get back to you soon.")


async def handle_answer_command(message: types.Message):
    """
    Used by an admin inside the support chat, replying to the complaint
    header message the bot posted there:
        /answer [text]
    Delivers the question + answer back to the original user. If the
    complaint originally came from a group, the answer is posted in that
    group with the user mentioned/tagged; if it came from a private chat,
    the answer is sent directly to the user. No media is sent back either way.
    """
    user = message.from_user
    if not user or user.id not in ADMIN_IDS:
        await message.reply("You are not authorized to use this command.")
        return

    if not SUPPORT_CHAT_ID or message.chat.id != SUPPORT_CHAT_ID:
        await message.reply("This command can only be used in the support chat.")
        return

    replied = message.reply_to_message
    if not replied:
        await message.reply("Reply to the complaint message in this chat with /answer [your reply].")
        return

    answer_text = message.text.partition(" ")[2].strip()
    if not answer_text:
        await message.reply("Usage: reply to the complaint message with /answer [your reply].")
        return

    complaint = get_complaint(replied.message_id)
    if not complaint:
        await message.reply("Could not find the original complaint for this message. Reply directly to the complaint message the bot posted.")
        return

    origin_chat_id = complaint.get("chat_id")
    origin_chat_type = complaint.get("chat_type")
    target_user_id = complaint.get("user_id")
    question_text = complaint.get("text") or "(see attached message)"
    user_name = complaint.get("user_name") or "there"

    body = (
        f"📬 <b>Support replied to your complaint</b>\n\n"
        f"<b>Question:</b> {html.escape(question_text)}\n"
        f"<b>Answer:</b> {html.escape(answer_text)}"
    )

    try:
        if origin_chat_type in ("group", "supergroup") and origin_chat_id:
            mention = f'<a href="tg://user?id={target_user_id}">{html.escape(user_name)}</a>'
            await message.bot.send_message(
                chat_id=origin_chat_id,
                text=f"{mention}\n\n{body}",
                parse_mode="HTML",
            )
        elif target_user_id:
            await message.bot.send_message(
                chat_id=target_user_id,
                text=body,
                parse_mode="HTML",
            )
        else:
            await message.reply("Could not determine where to deliver the answer.")
            return

        await message.reply("✅ Answer sent to the user.")
    except Exception:
        logging.exception("Failed to deliver answer to user")
        await message.reply("Failed to deliver the answer. The user may have blocked the bot.")