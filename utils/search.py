import difflib
import re
from typing import Any
from aiogram import types
try:
    from aiogram.types import (
        InputRichBlockButtons,
        InputRichBlockParagraph,
        InputRichMessage,
        RichMessageButton,
    )
    RICH_MESSAGE_AVAILABLE = True
except ImportError:
    InputRichBlockButtons = InputRichBlockParagraph = InputRichMessage = RichMessageButton = Any
    RICH_MESSAGE_AVAILABLE = False
from utils.helper import normalize_name, find_artifact_files
from utils.artifacts import find_artifact_info
from data.search_items import SEARCH_ITEMS

# aiogram 3.31.0 / Bot API 10.3: buttons in a rich message come in rows of
# up to this many, via InputRichBlockButtons ("<tg-button-row>").
_BUTTONS_PER_ROW = 2


def _normalize_query(value: str) -> str:
    return normalize_name(value or "")


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (value or "").lower())


def _matches_all_tokens(query_tokens: list[str], item_tokens: set[str]) -> bool:
    return all(
        any(qt == token or qt in token or token.startswith(qt) for token in item_tokens)
        for qt in query_tokens
    )


def search_catalog():
    """Separate identities prevent character/equipment name collisions."""
    from utils.cards import load_cards
    from utils.guides import load_guides
    from utils.artifacts import load_artifact_info
    from utils.weapons import load_weapons
    from utils.bosses import load_bosses
    result = {}
    for entry in load_cards() + load_guides():
        key = entry["character_key"]
        result["c:" + key] = entry.get("display_name") or (SEARCH_ITEMS.get(key) if normalize_name(SEARCH_ITEMS.get(key, "")) == normalize_name(key) else None) or key.replace("_", " ").title()
    result.update({"w:"+k: v.get("name", k) for k,v in load_weapons().items()})
    result.update({"a:"+k: v.get("name", k) for k,v in load_artifact_info().items()})
    result.update({"b:"+normalize_name(v["name"]): v["name"] for v in load_bosses()})
    return result


def find_search_matches(query: str, max_results: int = 24) -> list[str]:
    q = _normalize_query(query)
    if not q: return []
    scored = []
    for token, name in search_catalog().items():
        key = token.split(":", 1)[1]
        norm = _normalize_query(name)
        if q in key or q in norm:
            score = 0 if q in (key, norm) else 1
        else:
            ratio = max(difflib.SequenceMatcher(None,q,key).ratio(), difflib.SequenceMatcher(None,q,norm).ratio())
            if ratio < .65: continue
            score = 2 + (1-ratio)
        scored.append((score, token))
    scored.sort()
    # Reserve space per category so equipment cannot crowd out characters.
    matches = []
    for kind in ("c", "w", "a", "b"):
        matches.extend(t for _,t in [v for v in scored if v[1].startswith(kind+":")][:max(1,max_results//4)])
    return matches[:max_results]


def _search_result_buttons(keys: list[str], user_id: int) -> list[Any]:
    return [
        RichMessageButton(
            text=search_catalog().get(key, key.title()),
            callback_data=f"search|{user_id}|{key}",
        )
        for key in keys
    ]


def render_search_button_rows(keys: list[str], user_id: int) -> list[Any]:
    """Chunk search result buttons into <tg-button-row> blocks for a rich message."""
    buttons = _search_result_buttons(keys, user_id)
    rows = []

    for i in range(0, len(buttons), _BUTTONS_PER_ROW):
        rows.append(InputRichBlockButtons(buttons=buttons[i : i + _BUTTONS_PER_ROW]))

    return rows


def build_search_rich_message(query: str, keys: list[str], user_id: int) -> Any:
    """Build the rich message (text + button rows) shown for multiple /search matches."""
    blocks = [InputRichBlockParagraph(text=f'Search results for "{query}":')]
    for kind, title in (("c", "Characters"), ("w", "Weapons"), ("a", "Artifacts"), ("b", "Bosses")):
        group = [key for key in keys if key.startswith(kind+":")]
        if group:
            blocks.append(InputRichBlockParagraph(text=title))
            blocks.extend(render_search_button_rows(group, user_id))
    return InputRichMessage(blocks=blocks)


async def send_search_result(message: types.Message, key: str):
    from utils.bosses import find_boss
    from utils.helper import resolve_character_media
    from handlers.media import send_media_slideshow

    kind, separator, raw = key.partition(":")
    if separator and kind in ("c", "w", "a", "b"):
        key = raw
    else:
        kind = "c"  # Legacy buttons default to characters.
    if kind == "w":
        from utils.weapons import send_weapon_result
        await send_weapon_result(message, key)
        return
    if kind == "c":
        media_items = await resolve_character_media(message.bot, key)
        if not media_items:
            await message.reply("No character cards found.")
            return
        caption = search_catalog().get("c:"+key, key.title())
        await send_media_slideshow(message, media_items, caption=caption, character_key=key)
        return

    # --- Boss check ---
    display_name = search_catalog().get(kind+":"+key, key.title())
    boss = find_boss(display_name) if kind == "b" else None
    if boss and boss.get("file_id"):
        try:
            await message.reply_photo(
                photo=boss["file_id"],
                caption=f"<b>Boss:</b> {boss['name']}",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # --- Artifact check ---
    artifact_info = find_artifact_info(key) if kind == "a" else None
    artifact_files = find_artifact_files(key)

    if artifact_info or artifact_files:
        if artifact_info and artifact_info.get("image_url"):
            from html import escape
            title = escape(artifact_info.get("name", key))
            details = "\n\n".join(escape(str(artifact_info[p])) for p in ("2-Piece Effect", "4-Piece Effect") if p in artifact_info)
            await message.reply_photo(artifact_info["image_url"], caption=f"<b>{title}</b>\n\n{details}", parse_mode="HTML")
            return
        caption = None
        if artifact_info:
            info_lines = [f"<b>Artifact:</b> {artifact_info.get('name', key.title())}\n\n"]
            for part in ["2-Piece Effect", "4-Piece Effect"]:
                if part in artifact_info:
                    info_lines.append(f"<b>{part}</b>\n{artifact_info[part]}")
            caption = "\n\n".join(info_lines)

        if artifact_files:
            for idx, path in enumerate(artifact_files):
                try:
                    if idx == 0:
                        await message.reply_photo(
                            types.FSInputFile(path),
                            caption=caption,
                            parse_mode="HTML"
                        )
                    else:
                        await message.reply_photo(types.FSInputFile(path))
                except Exception:
                    pass
        if caption and not artifact_files:
            await message.reply(caption, parse_mode="HTML")
        return

    # --- Weapon check ---
    from utils.weapons import find_weapon, send_weapon_result as _send_weapon_result

    if find_weapon(key):
        await _send_weapon_result(message, key)
        return

    # --- Character cards + guides (with rich slideshow support) ---
    media_items = await resolve_character_media(message.bot, key)

    if not media_items:
        await message.reply(f"No files found for {key.title()}.")
        return

    caption = SEARCH_ITEMS.get(key, key.title())
    await send_media_slideshow(message, media_items, caption=caption, character_key=key)