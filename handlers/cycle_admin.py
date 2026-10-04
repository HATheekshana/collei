import logging

from aiogram import types

from data.config import ADMIN_IDS
from utils.helper import send_log
from utils.special_media import LABELS
from utils.cycle_state import CATEGORY_CONFIGS, ShiftResult, advance, retreat


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


def _format_result(result: ShiftResult, verb: str, category: str) -> str:
    label = LABELS.get(category, category.title())
    if not result.ok:
        return f"⚠️ {label}: {result.message}"
    return (
        f"✅ {label} {verb} -- current {result.old_current} → {result.new_current}, "
        f"next {result.old_next} → {result.new_next}"
    )


async def _run_shift(message: types.Message, category: str, direction: str):
    """direction: 'next' for /n<category> (advance), 'prev' for /p<category> (retreat)."""
    label = LABELS.get(category, category.title())
    verb = "advance" if direction == "next" else "retreat"
    command_name = f"{'n' if direction == 'next' else 'p'}{category}"

    if not is_admin(message):
        await message.reply("You are not authorized to use this command.")
        return

    if category not in CATEGORY_CONFIGS:
        await message.reply(f"Unknown category: {category}")
        return

    status_msg = await message.reply(f"⏳ /{command_name}: generating and shifting {label}...")

    try:
        if direction == "next":
            result = await advance(message.bot, category)
        else:
            result = await retreat(message.bot, category)
    except Exception:
        logging.exception("Cycle %s failed for %s", verb, category)
        await status_msg.edit_text(f"❌ /{command_name} failed unexpectedly. Check logs.")
        return

    text = _format_result(result, verb, category)
    await status_msg.edit_text(text)

    user = message.from_user
    username = f"@{user.username}" if user and user.username else "None"
    await send_log(
        message.bot,
        f"🔁 /{command_name} used\n\n"
        f"User: {user.full_name if user else 'Unknown'}\n"
        f"ID: {user.id if user else 'Unknown'}\n"
        f"Username: {username}\n\n"
        f"{text}",
    )


# ---------------------------------------------------------------------------
# Advance -- /nabyss  /ntheatre  /nstygian
# ---------------------------------------------------------------------------

async def handle_nabyss_command(message: types.Message):
    await _run_shift(message, "abyss", "next")


async def handle_ntheatre_command(message: types.Message):
    await _run_shift(message, "theatre", "next")


async def handle_nstygian_command(message: types.Message):
    await _run_shift(message, "stygian", "next")


# ---------------------------------------------------------------------------
# Retreat -- /pabyss  /ptheatre  /pstygian
# ---------------------------------------------------------------------------

async def handle_pabyss_command(message: types.Message):
    await _run_shift(message, "abyss", "prev")


async def handle_ptheatre_command(message: types.Message):
    await _run_shift(message, "theatre", "prev")


async def handle_pstygian_command(message: types.Message):
    await _run_shift(message, "stygian", "prev")
