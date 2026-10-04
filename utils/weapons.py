from typing import Any

from aiogram import types
from aiogram.types import InputMediaPhoto

try:
    from aiogram.types import (
        InputRichBlockButtons,
        InputRichBlockParagraph,
        InputRichBlockPhoto,
        InputRichBlockSectionHeading,
        InputRichMessage,
        RichMessageButton,
    )
    RICH_MESSAGE_AVAILABLE = True
except ImportError:
    InputRichBlockButtons = InputRichBlockParagraph = InputRichBlockPhoto = None
    InputRichBlockSectionHeading = InputRichMessage = RichMessageButton = None
    RICH_MESSAGE_AVAILABLE = False

from utils.helper import normalize_name

REFINEMENTS = ["R1", "R2", "R3", "R4", "R5"]
DEFAULT_REFINEMENT = "R1"

_weapons_cache = {}  # Loaded from MongoDB at startup and after updates.


def load_weapons() -> dict:
    """Return the in-memory MongoDB snapshot; never fall back to JSON."""
    return _weapons_cache


def weapon_search_items() -> dict:
    """key -> display name, for merging into SEARCH_ITEMS so /search and the
    inline query picker (which both key off SEARCH_ITEMS) pick up weapons."""
    return {key: entry.get("name", key) for key, entry in load_weapons().items()}


def find_weapon(query: str) -> dict | None:
    """Exact key match first (used by callbacks with the stored key), then a
    startswith match so partial names typed by the user still resolve."""
    normalized = normalize_name(query)
    weapons = load_weapons()

    if normalized in weapons:
        return weapons[normalized]

    for norm_name, entry in weapons.items():
        if norm_name.startswith(normalized):
            return entry

    return None


def weapon_key(entry: dict) -> str:
    return normalize_name(entry.get("name", ""))


def _format_main_stat(main_stat: dict | None) -> str | None:
    if not main_stat or not main_stat.get("name"):
        return None

    name = main_stat["name"]
    value = main_stat.get("value")
    if value is None:
        return name

    # Stat names like "CRIT DMG%" already carry the '%' — move it after the
    # value instead of doubling it up ("CRIT DMG: 88.2%" not "CRIT DMG%: 88.2%").
    if name.endswith("%"):
        return f"{name[:-1].strip()}: {value}%"
    return f"{name}: {value}"


def _refinement_text(entry: dict, refinement: str) -> tuple[str | None, str | None]:
    """Return (passive_name, refinement_text) for the given refinement, or
    (None, None) if this weapon has no passive (common for 1★/2★ weapons)."""
    passive = entry.get("passive") or {}
    passive_name = passive.get("name")
    refinements = passive.get("refinements") or {}
    text = refinements.get(refinement)
    if not passive_name or not text:
        return None, None
    return passive_name, text


def build_weapon_blocks(entry: dict, user_id: int, refinement: str = DEFAULT_REFINEMENT) -> list:
    """Blocks for a weapon's rich message: image, name, base stats, passive
    text at the given refinement, and R1-R5 buttons (if the weapon has a
    passive at all — plain/starter weapons don't)."""
    blocks = []

    image_url = entry.get("image_url")
    if image_url:
        blocks.append(InputRichBlockPhoto(photo=InputMediaPhoto(media=image_url)))

    blocks.append(InputRichBlockSectionHeading(text=entry.get("name", "Weapon"), size=3))

    level_90 = entry.get("level_90") or {}
    atk = level_90.get("atk")
    main_stat_line = _format_main_stat(level_90.get("main_stat"))

    stat_parts = []
    if atk is not None:
        stat_parts.append(f"Base ATK: {atk}")
    if main_stat_line:
        stat_parts.append(main_stat_line)
    if stat_parts:
        blocks.append(InputRichBlockParagraph(text="  •  ".join(stat_parts)))

    passive_name, refinement_text = _refinement_text(entry, refinement)
    if passive_name and refinement_text:
        blocks.append(InputRichBlockSectionHeading(text=f"{passive_name} ({refinement})", size=5))
        blocks.append(InputRichBlockParagraph(text=refinement_text))

        key = weapon_key(entry)
        buttons = [
            RichMessageButton(
                text=r,
                callback_data=f"weapon|{user_id}|{key}|{r}",
                style="primary" if r == refinement else None,
            )
            for r in REFINEMENTS if (entry.get('passive') or {}).get('refinements', {}).get(r)
        ]
        blocks.append(InputRichBlockButtons(buttons=buttons))

    return blocks


def build_weapon_rich_message(entry: dict, user_id: int, refinement: str = DEFAULT_REFINEMENT) -> Any:
    return InputRichMessage(blocks=build_weapon_blocks(entry, user_id, refinement))


async def send_weapon_result(message: types.Message, key: str, refinement: str = DEFAULT_REFINEMENT):
    entry = find_weapon(key)
    if not entry:
        await message.reply(f"No weapon found for {key.title()}.")
        return

    if refinement not in REFINEMENTS:
        refinement = DEFAULT_REFINEMENT

    if RICH_MESSAGE_AVAILABLE and hasattr(message, "reply_rich"):
        rich_message = build_weapon_rich_message(entry, message.from_user.id, refinement)
        await message.reply_rich(rich_message=rich_message)
        return

    await message.reply(
        build_weapon_html_caption(entry, refinement),
        parse_mode="HTML",
        reply_markup=build_weapon_classic_keyboard(entry, message.from_user.id, refinement),
    )


# ---------------------------------------------------------------------------
# Inline-mode variant.
#
# Bot API 10.3 restricts InputRichMessageContent (the rich-message content
# type for inline query results) to previously-uploaded files — it can't
# reference arbitrary external image URLs stored in MongoDB.
# So inline results use the same classic InlineQueryResultArticle + hidden
# preview link pattern this bot already uses for artifacts, with a classic
# InlineKeyboardMarkup for the R1-R5 buttons instead of RichMessageButton.
# Bot API 10.3 also added the same `style` field to InlineKeyboardButton, so
# the selected refinement is still highlighted the same way (style="primary").
# ---------------------------------------------------------------------------

def _hidden_url(url: str) -> str:
    return f'<a href="{url}">&#8203;</a>'


def build_weapon_html_caption(entry: dict, refinement: str = DEFAULT_REFINEMENT) -> str:
    name = entry.get("name", "Weapon")
    level_90 = entry.get("level_90") or {}
    atk = level_90.get("atk")
    main_stat_line = _format_main_stat(level_90.get("main_stat"))

    lines = [f"<b>{name}</b>"]

    image_url = entry.get("image_url")
    if image_url:
        lines.append(f"Preview:{_hidden_url(image_url)}")

    stat_parts = []
    if atk is not None:
        stat_parts.append(f"Base ATK: {atk}")
    if main_stat_line:
        stat_parts.append(main_stat_line)
    if stat_parts:
        lines.append("  •  ".join(stat_parts))

    passive_name, refinement_text = _refinement_text(entry, refinement)
    if passive_name and refinement_text:
        lines.append(f"<b>{passive_name}</b> ({refinement})\n{refinement_text}")

    return "\n\n".join(lines)


def build_weapon_classic_keyboard(entry: dict, user_id: int, refinement: str = DEFAULT_REFINEMENT):
    """InlineKeyboardMarkup version of the R1-R5 row, for surfaces (inline
    query results) that can't carry RichMessageButton. Returns None if this
    weapon has no passive to refine."""
    passive = entry.get("passive") or {}
    refinements = passive.get("refinements") or {}
    if not passive.get("name") or not any(refinements.get(r) for r in REFINEMENTS):
        return None

    key = weapon_key(entry)
    return types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(
                text=r,
                callback_data=f"wpni|{user_id}|{key}|{r}",
                style="primary" if r == refinement else None,
            )
            for r in REFINEMENTS if refinements.get(r)
        ]]
    )
