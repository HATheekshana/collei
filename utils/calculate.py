import asyncio
import logging
import os
import string
import threading
import time
from http.cookies import CookieError, SimpleCookie
from typing import Any

import requests
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from data.config import GENSHIN_SYNC_REGION, GENSHIN_SYNC_UID, HOYOLAB_COOKIES

try:
    from aiogram.types import (
        InputMediaPhoto,
        InputRichBlockButtons,
        InputRichBlockDetails,
        InputRichBlockParagraph,
        InputRichBlockPhoto,
        InputRichBlockSectionHeading,
        InputRichMessage,
        RichMessageButton,
    )
    RICH_MESSAGE_AVAILABLE = True
except ImportError:
    InputMediaPhoto = InputRichBlockButtons = InputRichBlockDetails = Any
    InputRichBlockParagraph = InputRichBlockPhoto = InputRichBlockSectionHeading = Any
    InputRichMessage = RichMessageButton = Any
    RICH_MESSAGE_AVAILABLE = False

router = Router()

LETTERS = list(string.ascii_uppercase)
CALC_PROMPT = "Calculator\n\nSelect the first letter of the character's name:"
CALC_AVATAR_URL = "https://sg-act-public-api.hoyolab.com/event/e20200928calculate/v1/avatar/list"
CALC_BATCH_COMPUTE_URL = "https://sg-act-public-api.hoyolab.com/event/e20200928calculate/v3/batch_compute"
_CALC_UID = GENSHIN_SYNC_UID
_CALC_CACHE = {"at": 0.0, "items": []}
_CALC_CACHE_TTL = 6 * 3600
_CALC_RUNNING: set[tuple[int, int]] = set()
_CALC_HTTP_SESSION = requests.Session()
_CALC_HTTP_SESSION_LOCK = threading.Lock()
_LEVEL_RANGES = [(start, min(start + 9, 90)) for start in range(1, 91, 10)]
_LEVEL_FIELDS = (
    ("level", "Character Level", "Lvl"),
    ("normal", "Normal Attack", "NA"),
    ("skill", "Elemental Skill", "Skill"),
    ("burst", "Burst", "Burst"),
)
_SECTIONS = (
    ("character", "Character Level", (0,)),
    ("talents", "Talents", (1, 2, 3)),
)


# --------------------------------------------------------------------------
# Start menu
# --------------------------------------------------------------------------

def build_calculate_rich_message(user_id: int) -> Any:
    blocks = [
        InputRichBlockParagraph(text="Calculator"),
        InputRichBlockParagraph(text="Select the first letter of the character's name:"),
    ]
    buttons = [
        RichMessageButton(text=letter, callback_data=f"calc|{user_id}|{letter}")
        for letter in LETTERS
    ]
    for index in range(0, len(buttons), 5):
        blocks.append(InputRichBlockButtons(buttons=buttons[index:index + 5]))
    return InputRichMessage(blocks=blocks)


def build_calculate_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    rows = [
        [
            types.InlineKeyboardButton(text=letter, callback_data=f"calc|{user_id}|{letter}")
            for letter in LETTERS[index:index + 6]
        ]
        for index in range(0, len(LETTERS), 6)
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


async def send_calculate_prompt(message: types.Message, user_id: int) -> None:
    if RICH_MESSAGE_AVAILABLE and hasattr(message, "reply_rich"):
        await message.reply_rich(rich_message=build_calculate_rich_message(user_id))
    else:
        await message.reply(CALC_PROMPT, reply_markup=build_calculate_keyboard(user_id))


# --------------------------------------------------------------------------
# HoYoLAB access
# --------------------------------------------------------------------------

def _calc_hoyolab_cookies() -> dict[str, str]:
    parsed_cookies = SimpleCookie()
    if HOYOLAB_COOKIES:
        try:
            parsed_cookies.load(HOYOLAB_COOKIES)
        except CookieError as error:
            raise ValueError("HOYOLAB_COOKIES is malformed.") from error

    cookies = {
        name: morsel.value
        for name, morsel in parsed_cookies.items()
    }
    if "ltuid" in cookies and "ltuid_v2" not in cookies:
        cookies["ltuid_v2"] = cookies["ltuid"]
    if "ltoken" in cookies and "ltoken_v2" not in cookies:
        cookies["ltoken_v2"] = cookies["ltoken"]

    for env_name, cookie_name in (
        ("HOYOLAB_LTUID", "ltuid_v2"),
        ("HOYOLAB_LTOKEN", "ltoken_v2"),
        ("HOYOLAB_LTMID", "ltmid_v2"),
        ("HOYOLAB_COOKIE_TOKEN", "cookie_token_v2"),
        ("HOYOLAB_ACCOUNT_ID", "account_id_v2"),
        ("HOYOLAB_ACCOUNT_MID", "account_mid_v2"),
        ("HOYOLAB_DEVICE_ID", "_HYVUUID"),
    ):
        value = os.getenv(env_name)
        if value:
            cookies[cookie_name] = value

    missing_cookies = {"ltuid_v2", "ltoken_v2"} - cookies.keys()
    if missing_cookies:
        raise ValueError(
            "Calculator needs HoYoLAB authentication. Missing cookie names: "
            f"{', '.join(sorted(missing_cookies))}. Set HOYOLAB_COOKIES or "
            "HOYOLAB_LTUID and HOYOLAB_LTOKEN."
        )
    return cookies


def _calc_session_post(url: str, **kwargs: Any) -> requests.Response:
    cookies = kwargs.pop("cookies", None)
    with _CALC_HTTP_SESSION_LOCK:
        _CALC_HTTP_SESSION.cookies.clear()
        if cookies:
            _CALC_HTTP_SESSION.cookies.update(cookies)
        return _CALC_HTTP_SESSION.post(url, **kwargs)


def _fetch_calc_characters_sync():
    payload = {
        "element_attr_ids": [],
        "weapon_cat_ids": [],
        "page": 1,
        "size": 1000,
        "is_all": True,
        "lang": "en-us",
    }
    headers = {
        "Origin": "https://act.hoyolab.com",
        "Referer": "https://act.hoyolab.com/",
        "x-rpc-lang": "en-us",
        "Content-Type": "application/json",
    }
    cookies = _calc_hoyolab_cookies()
    response = _calc_session_post(
        CALC_AVATAR_URL,
        json=payload,
        headers=headers,
        cookies=cookies,
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("retcode") != 0:
        raise RuntimeError(
            f"HoYoLAB retcode={body.get('retcode')} message={body.get('message')}"
        )
    data = body.get("data") or {}
    raw = data.get("list") or data.get("avatars") or []
    items, seen = [], set()
    for entry in raw:
        name = str(entry.get("name") or "").strip()
        character_id = entry.get("id")
        if not name or character_id is None or character_id in seen:
            continue
        seen.add(character_id)
        items.append({
            "id": int(character_id),
            "name": name,
            "element_attr_id": entry.get("element_attr_id"),
            "avatar_level": entry.get("avatar_level", entry.get("level", 1)),
            "skill_list": entry.get("skill_list") or [],
        })
    items.sort(key=lambda item: item["name"].lower())
    return items


async def get_calc_characters():
    now = time.time()
    if _CALC_CACHE["items"] and now - _CALC_CACHE["at"] < _CALC_CACHE_TTL:
        return _CALC_CACHE["items"]
    try:
        items = await asyncio.to_thread(_fetch_calc_characters_sync)
    except Exception:
        logging.exception("Failed to fetch calculator character list")
        return _CALC_CACHE["items"]
    if items:
        _CALC_CACHE.update(at=now, items=items)
    return items


def _calc_api_region(region: str) -> str:
    region_code = (region or "").strip().lower()
    aliases = {
        "asia": "os_asia",
        "america": "os_usa",
        "na": "os_usa",
        "europe": "os_euro",
        "eu": "os_euro",
        "sar": "os_cht",
        "tw": "os_cht",
        "hk": "os_cht",
    }
    region_code = aliases.get(region_code, region_code)
    if region_code not in {"os_asia", "os_usa", "os_euro", "os_cht"}:
        raise ValueError("Unsupported Genshin server region for calculator.")
    return region_code


def _skill_gid(skill: dict[str, Any]) -> int:
    # batch_compute wants group_id (e.g. 10031), not id (e.g. 11001)
    return int(skill.get("group_id") or skill["id"])


def _build_calc_compute_payload(
    character: dict[str, Any],
    current_levels: list[int],
    target_levels: list[int],
) -> dict[str, Any]:
    if not _CALC_UID:
        raise ValueError("Set GENSHIN_SYNC_UID to calculate materials.")
    try:
        element_attr_id = int(character["element_attr_id"])
        avatar_id = int(character["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Calculator character metadata is incomplete.") from error

    skills = [s for s in character.get("skill_list", []) if isinstance(s, dict)]
    upgradeable = [
        s for s in skills
        if not s.get("is_proud") and int(s.get("max_level", 0)) > 1
    ][:3]
    if len(upgradeable) != 3:
        raise ValueError("Could not load all three talent records for this character.")

    try:
        selected = {
            _skill_gid(skill): (current_levels[i], target_levels[i])
            for i, skill in enumerate(upgradeable, start=1)
        }
        skill_items = []
        for skill in skills:
            gid = _skill_gid(skill)
            current, target = selected.get(gid, (1, 1))
            skill_items.append({
                "id": gid,
                "level_current": current,
                "level_target": target,
            })
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Calculator talent metadata is incomplete.") from error

    return {
        "items": [{
            "avatar_id": avatar_id,
            "avatar_level_current": current_levels[0],
            "avatar_level_target": target_levels[0],
            "element_attr_id": element_attr_id,
            "from_user_sync": False,
            "skill_list": skill_items,
        }],
        "lang": "en-us",
        "region": _calc_api_region(GENSHIN_SYNC_REGION),
        "uid": str(_CALC_UID),
    }


def _fetch_calc_materials_sync(payload: dict[str, Any]) -> dict[str, Any]:
    cookies = _calc_hoyolab_cookies()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://act.hoyolab.com",
        "Referer": "https://act.hoyolab.com/",
        "x-rpc-lang": "en-us",
        "x-rpc-cal_type": "0",
        "x-rpc-stat_platform": "PC",
    }
    if device_id := cookies.get("_HYVUUID"):
        headers["x-rpc-device_id"] = device_id

    body, response = {}, None
    for attempt in range(3):
        response = _calc_session_post(
            CALC_BATCH_COMPUTE_URL,
            json=payload,
            headers=headers,
            cookies=cookies,
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("retcode") == -500001 and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        break

    if body.get("retcode") != 0:
        raise RuntimeError(
            f"HoYoLAB calculator returned HTTP {response.status_code}, "
            f"retcode={body.get('retcode')}: {body.get('message')}"
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("HoYoLAB calculator returned no material data.")
    return data


# --------------------------------------------------------------------------
# Calculation (character and talents are computed separately)
# --------------------------------------------------------------------------

def _part_indexes(part: str) -> tuple[int, ...]:
    return (0,) if part == "character" else (1, 2, 3)


def _part_changed(current_levels: list[int], target_levels: list[int], part: str) -> bool:
    return any(target_levels[i] > current_levels[i] for i in _part_indexes(part))


def _part_levels(current_levels: list[int], target_levels: list[int], part: str):
    # Everything outside this part (or skipped) is sent as 1 -> 1, which costs nothing.
    cur, tgt = [1, 1, 1, 1], [1, 1, 1, 1]
    for i in _part_indexes(part):
        if target_levels[i] > current_levels[i]:
            cur[i], tgt[i] = current_levels[i], target_levels[i]
    return cur, tgt


async def calculate_materials_split(
    character: dict[str, Any],
    current_levels: list[int],
    target_levels: list[int],
) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for part, _, _ in _SECTIONS:
        if not _part_changed(current_levels, target_levels, part):
            sections[part] = None
            continue
        cur, tgt = _part_levels(current_levels, target_levels, part)
        payload = _build_calc_compute_payload(character, cur, tgt)
        sections[part] = await asyncio.to_thread(_fetch_calc_materials_sync, payload)
    return sections


def _material_entries(data: dict[str, Any] | None) -> list[tuple[str, int, str]]:
    entries = []
    for material in (data or {}).get("overall_consume") or []:
        if not isinstance(material, dict):
            continue
        name = str(material.get("name") or "").strip()
        try:
            amount = int(material.get("num", 0))
        except (TypeError, ValueError):
            continue
        if name and amount > 0:
            entries.append((name, amount, str(material.get("icon") or "").strip()))
    return entries


def format_calc_materials(
    sections: dict[str, Any],
    character_name: str,
    current_levels: list[int],
    target_levels: list[int],
) -> str:
    lines = [f"{character_name} · Upgrade Materials"]
    total = 0
    for part, title, indexes in _SECTIONS:
        entries = _material_entries(sections.get(part))
        if not entries:
            continue
        total += len(entries)
        lines += ["", f"{title}:"]
        for i in indexes:
            if target_levels[i] > current_levels[i]:
                lines.append(f"{_LEVEL_FIELDS[i][1]}: {current_levels[i]} → {target_levels[i]}")
        lines.append("")
        lines.extend(f"• {name}: {amount:,}" for name, amount, _ in entries)
    if not total:
        raise RuntimeError("HoYoLAB calculator returned an empty materials list.")
    return "\n".join(lines)


def _md_escape(text: str) -> str:
    for ch in ("\\", "*", "_", "`", "[", "]", "|", "~", "<", ">"):
        text = text.replace(ch, "\\" + ch)
    return text


def build_materials_markdown(
    sections: dict[str, Any],
    character_name: str,
    current_levels: list[int],
    target_levels: list[int],
) -> str:
    lines = [f"# {_md_escape(character_name)} · Upgrade Materials"]
    total = 0
    for part, title, indexes in _SECTIONS:
        entries = _material_entries(sections.get(part))
        if not entries:
            continue
        total += len(entries)
        changes = " · ".join(
            f"**{_LEVEL_FIELDS[i][1]}:** {current_levels[i]} → {target_levels[i]}"
            for i in indexes if target_levels[i] > current_levels[i]
        )
        lines += ["", f"## {title}", "", changes, ""]
        for name, amount, icon in entries:
            label = _md_escape(name)
            image = f"![{label}]({icon}) " if icon.startswith("https://") else ""
            lines.append(f"- {image}{label} × **{amount:,}**")
    if not total:
        raise RuntimeError("HoYoLAB calculator returned an empty materials list.")
    return "\n".join(lines)


def _details_block(summary: str, blocks: list[Any]) -> Any:
    # Collapsed by default: the user taps a material to see its icon and amount.
    return InputRichBlockDetails(summary=summary, blocks=blocks)


def build_materials_rich_message(
    sections: dict[str, Any],
    character_name: str,
    current_levels: list[int],
    target_levels: list[int],
) -> InputRichMessage:
    blocks = [InputRichBlockSectionHeading(text=f"{character_name} · Upgrade Materials", size=3)]
    total = 0
    for part, title, indexes in _SECTIONS:
        entries = _material_entries(sections.get(part))
        if not entries:
            continue
        total += len(entries)
        changes = " · ".join(
            f"{_LEVEL_FIELDS[i][1]}: {current_levels[i]} → {target_levels[i]}"
            for i in indexes if target_levels[i] > current_levels[i]
        )
        if changes:
            blocks.append(InputRichBlockParagraph(text=f"{title}: {changes}"))
        else:
            blocks.append(InputRichBlockParagraph(text=title))
        for name, amount, icon in entries:
            item_blocks = []
            if icon.startswith("https://"):
                item_blocks.append(InputRichBlockPhoto(photo=InputMediaPhoto(media=icon)))
            item_blocks.append(InputRichBlockParagraph(text=f"{name}: {amount:,}"))
            blocks.append(_details_block(f"{name} × {amount:,}", item_blocks))
    if not total:
        raise RuntimeError("HoYoLAB calculator returned an empty materials list.")
    return InputRichMessage(blocks=blocks)


def _edit_rich_markdown_sync(token: str, chat_id: int, message_id: int, markdown: str) -> None:
    # Never retry: a timed-out edit may already have been applied.
    response = requests.post(
        f"https://api.telegram.org/bot{token}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "rich_message": {"markdown": markdown},
        },
        timeout=(10, 40),
    )
    body = response.json()
    if not body.get("ok"):
        description = body.get("description", "editMessageText failed")
        if "message is not modified" in description.lower():
            return
        raise RuntimeError(description)


# --------------------------------------------------------------------------
# Character selection UI
# --------------------------------------------------------------------------

def _character_keyboard(user_id: int, characters: list[dict[str, Any]]):
    rows = [
        [types.InlineKeyboardButton(
            text=character["name"],
            callback_data=f"calcc|{user_id}|{character['id']}",
        )]
        for character in characters
    ]
    rows.append([
        types.InlineKeyboardButton(text="‹ Letters", callback_data=f"calc|{user_id}|back")
    ])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


def _character_rich_message(user_id: int, letter: str, characters: list[dict[str, Any]]):
    blocks = [InputRichBlockParagraph(text=f"Characters starting with {letter}:")]
    buttons = [
        RichMessageButton(
            text=character["name"],
            callback_data=f"calcc|{user_id}|{character['id']}",
        )
        for character in characters
    ]
    for index in range(0, len(buttons), 2):
        blocks.append(InputRichBlockButtons(buttons=buttons[index:index + 2]))
    blocks.append(InputRichBlockButtons(buttons=[
        RichMessageButton(text="‹ Letters", callback_data=f"calc|{user_id}|back")
    ]))
    return InputRichMessage(blocks=blocks)


# --------------------------------------------------------------------------
# Level helpers
# --------------------------------------------------------------------------

def _valid_levels(value: str):
    try:
        levels = [int(level) for level in value.split(",")]
    except (AttributeError, ValueError):
        return None
    if len(levels) != len(_LEVEL_FIELDS):
        return None
    if any(level < 0 or level > (90 if index == 0 else 10)
           for index, level in enumerate(levels)):
        return None
    return levels


def _levels_string(levels: list[int]) -> str:
    return ",".join(map(str, levels))


def _available_level_ranges(stage: str, levels: list[int]):
    if stage == "target":
        return [
            (start, end) for start, end in _LEVEL_RANGES
            if end > levels[0]
        ]
    return _LEVEL_RANGES


def _level_range_label(stage: str, levels: list[int], start: int, end: int) -> str:
    if stage == "target":
        start = max(start, levels[0] + 1)
    return f"{start}-{end}"


def _next_range_start(level: int) -> int:
    # Start of the 10-level range that contains level + 1.
    return 81 if level >= 90 else (level // 10) * 10 + 1


def _current_range_start(level: int) -> int:
    # Start of the range that contains this level itself.
    return ((max(level, 1) - 1) // 10) * 10 + 1


def _back_letter(character_id: str) -> str:
    # First letter of the character's name, so Back returns to that letter's list.
    name = next(
        (item["name"] for item in _CALC_CACHE["items"] if str(item["id"]) == character_id),
        "",
    )
    return name[:1].upper() or "back"


# --------------------------------------------------------------------------
# Range prompt (with Back and Skip)
# --------------------------------------------------------------------------

def _range_skip_data(user_id: int, character_id: str, levels: list[int]) -> str:
    return f"calcrange|{user_id}|{character_id}|target|{_levels_string(levels)}|level|0"


def _current_range_back_data(user_id: int, character_id: str, range_start: int, levels: list[int]) -> str:
    return f"calcback|{user_id}|{character_id}|currentrange|{range_start}|{_levels_string(levels)}"


def _current_details_back_data(user_id: int, character_id: str, range_start: int, levels: list[int]) -> str:
    return f"calcback|{user_id}|{character_id}|currentdetails|{range_start}|{_levels_string(levels)}"


def _target_range_back_data(user_id: int, character_id: str, range_start: int, levels: list[int]) -> str:
    if levels[0] >= 90:
        return _current_details_back_data(
            user_id, character_id, _current_range_start(90), levels,
        )
    return f"calcback|{user_id}|{character_id}|targetrange|{range_start}|{_levels_string(levels)}"


def _range_keyboard(user_id: int, character_id: str, stage: str, levels: list[int]):
    rows = [[types.InlineKeyboardButton(
        text=_level_range_label(stage, levels, start, end),
        callback_data=(
            f"calcrange|{user_id}|{character_id}|{stage}|{_levels_string(levels)}"
            f"|level|{start}"
        ),
    )] for start, end in _available_level_ranges(stage, levels)]
    if stage == "target":
        rows.append([types.InlineKeyboardButton(
            text="Back",
            callback_data=_current_details_back_data(
                user_id, character_id, _current_range_start(levels[0]), levels,
            ),
        )])
        rows.append([types.InlineKeyboardButton(
            text="Skip character level",
            callback_data=_range_skip_data(user_id, character_id, levels),
        )])
    else:
        rows.append([types.InlineKeyboardButton(
            text="Back",
            callback_data=f"calc|{user_id}|{_back_letter(character_id)}",
        )])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


def _range_rich_message(
    user_id: int,
    character_id: str,
    stage: str,
    levels: list[int],
    prompt: str,
):
    blocks = [InputRichBlockParagraph(text=prompt)]
    buttons = [
        RichMessageButton(
            text=_level_range_label(stage, levels, start, end),
            callback_data=(
                f"calcrange|{user_id}|{character_id}|{stage}|{_levels_string(levels)}"
                f"|level|{start}"
            ),
        )
        for start, end in _available_level_ranges(stage, levels)
    ]
    for index in range(0, len(buttons), 5):
        blocks.append(InputRichBlockButtons(buttons=buttons[index:index + 5]))
    if stage == "target":
        blocks.append(InputRichBlockButtons(buttons=[
            RichMessageButton(
                text="Back",
                callback_data=_current_details_back_data(
                    user_id, character_id, _current_range_start(levels[0]), levels,
                ),
            ),
        ]))
        blocks.append(InputRichBlockButtons(buttons=[RichMessageButton(
            text="Skip character level",
            callback_data=_range_skip_data(user_id, character_id, levels),
        )]))
    else:
        blocks.append(InputRichBlockButtons(buttons=[RichMessageButton(
            text="Back",
            callback_data=f"calc|{user_id}|{_back_letter(character_id)}",
        )]))
    return InputRichMessage(blocks=blocks)


async def _send_range_prompt(
    callback: types.CallbackQuery,
    prompt: str,
    character_id: str,
    stage: str,
    levels: list[int],
):
    user_id = callback.from_user.id
    if RICH_MESSAGE_AVAILABLE and callback.message and hasattr(callback.message, "answer_rich"):
        await _send_callback_message(
            callback,
            prompt,
            rich_message=_range_rich_message(
                user_id, character_id, stage, levels, prompt,
            ),
        )
    else:
        await _send_callback_message(
            callback,
            prompt,
            _range_keyboard(user_id, character_id, stage, levels),
        )


# --------------------------------------------------------------------------
# Current details
# --------------------------------------------------------------------------

def _current_details_keyboard(
    user_id: int, character_id: str, range_start: int, levels: list[int],
):
    rows = []
    for index, (field, _, _) in enumerate(_LEVEL_FIELDS):
        first, last = (
            (range_start, min(range_start + 9, 90))
            if field == "level"
            else (1, 10)
        )
        options = [
            types.InlineKeyboardButton(
                text=str(level),
                callback_data=(
                    f"calccurrent|{user_id}|{character_id}|{range_start}|{field}|{level}"
                    f"|{_levels_string(levels)}"
                ),
                style="primary" if levels[index] == level else None,
            )
            for level in range(first, last + 1)
        ]
        rows.extend(options[offset:offset + 5] for offset in range(0, len(options), 5))
    rows.append([types.InlineKeyboardButton(
        text="Back",
        callback_data=_current_range_back_data(user_id, character_id, range_start, levels),
    )])
    rows.append([types.InlineKeyboardButton(
        text="Done",
        callback_data=(
            f"calcdone|{user_id}|{character_id}|{range_start}|{_levels_string(levels)}"
        ),
    )])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


def _current_details_rich_message(
    user_id: int, character_id: str, range_start: int, levels: list[int],
):
    character_name = next(
        (item["name"] for item in _CALC_CACHE["items"]
         if str(item["id"]) == character_id),
        character_id,
    )
    blocks = [
        InputRichBlockSectionHeading(text=f"{character_name} · Current Details", size=3),
        InputRichBlockParagraph(
            text=f"Choose the current levels. Character range: "
            f"{range_start}-{min(range_start + 9, 90)}."
        ),
    ]
    for index, (field, label, _) in enumerate(_LEVEL_FIELDS):
        blocks.append(InputRichBlockSectionHeading(text=label, size=5))
        first, last = (
            (range_start, min(range_start + 9, 90))
            if field == "level"
            else (1, 10)
        )
        buttons = [
            RichMessageButton(
                text=str(level),
                callback_data=(
                    f"calccurrent|{user_id}|{character_id}|{range_start}|{field}|{level}"
                    f"|{_levels_string(levels)}"
                ),
                style="primary" if levels[index] == level else None,
            )
            for level in range(first, last + 1)
        ]
        for offset in range(0, len(buttons), 5):
            blocks.append(InputRichBlockButtons(buttons=buttons[offset:offset + 5]))
    blocks.append(InputRichBlockButtons(buttons=[
        RichMessageButton(
            text="Back",
            callback_data=_current_range_back_data(user_id, character_id, range_start, levels),
        )
    ]))
    blocks.append(InputRichBlockButtons(buttons=[
        RichMessageButton(
            text="Done",
            callback_data=(
                f"calcdone|{user_id}|{character_id}|{range_start}|{_levels_string(levels)}"
            ),
            style="success",
        )
    ]))
    blocks.append(InputRichBlockParagraph(
        text="Choose one level in each section. Selected levels are highlighted."
    ))
    return InputRichMessage(blocks=blocks)


def _current_details_text(character_id: str, range_start: int) -> str:
    character_name = next(
        (item["name"] for item in _CALC_CACHE["items"]
         if str(item["id"]) == character_id),
        character_id,
    )
    return (
        f"{character_name} — Current Details\n\n"
        f"Choose the current levels. Character range: "
        f"{range_start}-{min(range_start + 9, 90)}.\n\n"
        "Character Level\nNormal Attack\nElemental Skill\nBurst\n\n"
        "Selected levels are highlighted."
    )


async def _send_current_details(
    callback: types.CallbackQuery,
    character_id: str,
    range_start: int,
    levels: list[int],
    edit_in_place: bool = False,
):
    markup = _current_details_keyboard(
        callback.from_user.id, character_id, range_start, levels,
    )
    if RICH_MESSAGE_AVAILABLE and callback.message and hasattr(callback.message, "answer_rich"):
        rich_message = _current_details_rich_message(
            callback.from_user.id, character_id, range_start, levels,
        )
        if edit_in_place:
            try:
                await callback.bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    rich_message=rich_message,
                )
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
        else:
            await _send_callback_message(
                callback,
                _current_details_text(character_id, range_start),
                rich_message=rich_message,
            )
    elif callback.message:
        if edit_in_place:
            try:
                await callback.message.edit_reply_markup(reply_markup=markup)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
        else:
            await _send_callback_message(
                callback,
                _current_details_text(character_id, range_start),
                markup,
            )


# --------------------------------------------------------------------------
# Target details (with Skip rows)
# --------------------------------------------------------------------------

def _ct_data(user_id, character_id, range_start, current_levels, target_levels, field, target):
    return (
        f"ct|{user_id}|{character_id}|{range_start}|"
        f"{_levels_string(current_levels)}|{_levels_string(target_levels)}|"
        f"{field[0]}|{target}"
    )


def _target_details_keyboard(
    user_id: int,
    character_id: str,
    range_start: int,
    current_levels: list[int],
    target_levels: list[int],
):
    rows = []
    for index, (field, _, _) in enumerate(_LEVEL_FIELDS):
        first, last = (
            (range_start, min(range_start + 9, 90)) if field == "level" else (1, 10)
        )
        options = [
            types.InlineKeyboardButton(
                text=str(target),
                callback_data=_ct_data(
                    user_id, character_id, range_start,
                    current_levels, target_levels, field, target,
                ),
                style="primary" if target_levels[index] == target else None,
            )
            for target in range(max(first, current_levels[index] + 1), last + 1)
        ]
        rows.extend(options[offset:offset + 5] for offset in range(0, len(options), 5))
        rows.append([types.InlineKeyboardButton(
            text="Skip",
            callback_data=_ct_data(
                user_id, character_id, range_start,
                current_levels, target_levels, field, current_levels[index],
            ),
            style="primary" if target_levels[index] == current_levels[index] else None,
        )])
    rows.append([types.InlineKeyboardButton(
        text="Back",
        callback_data=_target_range_back_data(user_id, character_id, range_start, current_levels),
    )])
    rows.append([types.InlineKeyboardButton(
        text="Done",
        callback_data=(
            f"ctd|{user_id}|{character_id}|{_levels_string(current_levels)}|"
            f"{_levels_string(target_levels)}|{range_start}"
        ),
    )])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


def _target_details_rich_message(
    user_id: int,
    character_id: str,
    range_start: int,
    current_levels: list[int],
    target_levels: list[int],
):
    character_name = next(
        (item["name"] for item in _CALC_CACHE["items"]
         if str(item["id"]) == character_id),
        character_id,
    )
    blocks = [
        InputRichBlockSectionHeading(text=f"{character_name} · Target Details", size=3),
        InputRichBlockParagraph(
            text=f"Choose target levels above your current levels, or Skip. "
            f"Character range: {range_start}-{min(range_start + 9, 90)}."
        ),
    ]
    for index, (field, label, _) in enumerate(_LEVEL_FIELDS):
        blocks.append(InputRichBlockSectionHeading(
            text=f"{label} · Current {current_levels[index]}", size=5,
        ))
        first, last = (
            (range_start, min(range_start + 9, 90)) if field == "level" else (1, 10)
        )
        buttons = [
            RichMessageButton(
                text=str(target),
                callback_data=_ct_data(
                    user_id, character_id, range_start,
                    current_levels, target_levels, field, target,
                ),
                style="primary" if target_levels[index] == target else None,
            )
            for target in range(max(first, current_levels[index] + 1), last + 1)
        ]
        for offset in range(0, len(buttons), 5):
            blocks.append(InputRichBlockButtons(buttons=buttons[offset:offset + 5]))
        blocks.append(InputRichBlockButtons(buttons=[RichMessageButton(
            text="Skip",
            callback_data=_ct_data(
                user_id, character_id, range_start,
                current_levels, target_levels, field, current_levels[index],
            ),
            style="primary" if target_levels[index] == current_levels[index] else None,
        )]))
    blocks.append(InputRichBlockButtons(buttons=[
        RichMessageButton(
            text="Back",
            callback_data=_target_range_back_data(user_id, character_id, range_start, current_levels),
        )
    ]))
    blocks.append(InputRichBlockButtons(buttons=[
        RichMessageButton(
            text="Done",
            callback_data=(
                f"ctd|{user_id}|{character_id}|{_levels_string(current_levels)}|"
                f"{_levels_string(target_levels)}|{range_start}"
            ),
            style="success",
        )
    ]))
    return InputRichMessage(blocks=blocks)


async def _send_target_details(
    callback: types.CallbackQuery,
    character_id: str,
    range_start: int,
    current_levels: list[int],
    target_levels: list[int],
    edit_in_place: bool = False,
):
    markup = _target_details_keyboard(
        callback.from_user.id, character_id, range_start, current_levels, target_levels,
    )
    if RICH_MESSAGE_AVAILABLE and callback.message and hasattr(callback.message, "answer_rich"):
        rich_message = _target_details_rich_message(
            callback.from_user.id, character_id, range_start, current_levels, target_levels,
        )
        if edit_in_place:
            try:
                await callback.bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    rich_message=rich_message,
                )
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
        else:
            await _send_callback_message(
                callback,
                "Choose target levels for the character and talents.",
                rich_message=rich_message,
            )
    elif callback.message:
        if edit_in_place:
            try:
                await callback.message.edit_reply_markup(reply_markup=markup)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
        else:
            await _send_callback_message(
                callback,
                "Choose target levels for the character and talents.",
                markup,
            )


# --------------------------------------------------------------------------
# Shared callback helpers
# --------------------------------------------------------------------------

async def _payload(callback: types.CallbackQuery, prefix: str):
    parts = (callback.data or "").split("|")
    if len(parts) < 3 or parts[0] != prefix:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return None
    try:
        owner_id = int(parts[1])
    except ValueError:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return None
    if owner_id != callback.from_user.id:
        await callback.answer("This button is not for you.", show_alert=True)
        return None
    return parts[2:]


async def _send_callback_message(
    callback: types.CallbackQuery,
    text: str,
    reply_markup: types.InlineKeyboardMarkup | None = None,
    rich_message: Any = None,
):
    """Edit the tapped message in place; only send + delete if editing fails."""
    message = callback.message
    if message is None:
        return
    try:
        if rich_message is not None and hasattr(message, "answer_rich"):
            await callback.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                rich_message=rich_message,
                reply_markup=reply_markup,
            )
        else:
            await callback.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text=text,
                reply_markup=reply_markup,
            )
        return
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return
        logging.debug("Edit failed, sending a new message instead", exc_info=True)
    except Exception:
        logging.debug("Edit failed, sending a new message instead", exc_info=True)

    if rich_message is not None and hasattr(message, "answer_rich"):
        await message.answer_rich(rich_message=rich_message, reply_markup=reply_markup)
    else:
        await callback.bot.send_message(
            chat_id=message.chat.id, text=text, reply_markup=reply_markup,
        )
    if hasattr(message, "delete"):
        try:
            await message.delete()
        except Exception:
            logging.debug("Could not delete previous calculator message", exc_info=True)


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------

@router.callback_query(lambda query: query.data and query.data.startswith("calc|"))
async def handle_calculate_letter(callback: types.CallbackQuery):
    payload = await _payload(callback, "calc")
    if payload is None:
        return
    if len(payload) != 1 or callback.message is None:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    value = payload[0]
    user_id = callback.from_user.id
    await callback.answer()
    if value == "back":
        if RICH_MESSAGE_AVAILABLE and hasattr(callback.message, "answer_rich"):
            await _send_callback_message(
                callback, CALC_PROMPT, rich_message=build_calculate_rich_message(user_id),
            )
        else:
            await _send_callback_message(
                callback, CALC_PROMPT, build_calculate_keyboard(user_id),
            )
        return

    letter = value.upper()
    if len(letter) != 1 or letter not in LETTERS:
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="This character letter is invalid. Please start /calculate again.",
        )
        return
    characters = await get_calc_characters()
    if not characters:
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Could not load the character list. Try again later.",
        )
        return
    matches = [character for character in characters
               if character["name"].upper().startswith(letter)]
    if not matches:
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=f"No characters start with {letter}.",
        )
        return
    if RICH_MESSAGE_AVAILABLE and hasattr(callback.message, "answer_rich"):
        await _send_callback_message(
            callback,
            f"Characters starting with {letter}:",
            rich_message=_character_rich_message(user_id, letter, matches),
        )
    else:
        await _send_callback_message(
            callback,
            f"Characters starting with {letter}:",
            _character_keyboard(user_id, matches),
        )


@router.callback_query(lambda query: query.data and query.data.startswith("calcc|"))
async def handle_calculate_character(callback: types.CallbackQuery):
    payload = await _payload(callback, "calcc")
    if payload is None:
        return
    if len(payload) != 1 or callback.message is None:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    character_id = payload[0]
    character = next(
        (item for item in _CALC_CACHE["items"] if str(item["id"]) == character_id),
        None,
    )
    if character is None:
        await callback.answer("Character data expired. Please start /calculate again.", show_alert=True)
        return
    levels = [0, 0, 0, 0]
    await callback.answer()
    await _send_range_prompt(
        callback,
        f"{character['name']}\n\nCharacter Level\nSelect the current level range:",
        character_id,
        "current",
        levels,
    )


@router.callback_query(lambda query: query.data and query.data.startswith("calcrange|"))
async def handle_calculate_range(callback: types.CallbackQuery):
    payload = await _payload(callback, "calcrange")
    if payload is None:
        return
    if len(payload) != 5:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    character_id, stage, state, field, range_value = payload
    levels = _valid_levels(state)
    try:
        range_start = int(range_value)
    except ValueError:
        range_start = -1
    valid_ranges = {start for start, _ in _LEVEL_RANGES}
    skip = stage == "target" and range_start == 0
    if (levels is None or field != "level" or stage not in {"current", "target"}
            or (range_start not in valid_ranges and not skip)):
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    if stage == "target" and any(level == 0 for level in levels):
        await callback.answer(
            "Current levels are missing. Please start /calculate again.",
            show_alert=True,
        )
        return
    if skip:
        await callback.answer()
        await _send_target_details(
            callback, character_id, _next_range_start(levels[0]), levels, list(levels),
        )
        return
    if stage == "target" and range_start not in {
        start for start, _ in _available_level_ranges(stage, levels)
    }:
        await callback.answer(
            "Choose a target range above the current character level.",
            show_alert=True,
        )
        return
    await callback.answer()
    if stage == "current":
        if not range_start <= levels[0] <= min(range_start + 9, 90):
            levels[0] = 0
        await _send_current_details(callback, character_id, range_start, levels)
        return
    await _send_target_details(
        callback, character_id, range_start, levels, list(levels),
    )


@router.callback_query(lambda query: query.data and query.data.startswith("calcback|"))
async def handle_calculate_back(callback: types.CallbackQuery):
    payload = await _payload(callback, "calcback")
    if payload is None:
        return
    if len(payload) != 4:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    character_id, step, range_value, state = payload
    levels = _valid_levels(state)
    try:
        range_start = int(range_value)
    except ValueError:
        range_start = 0
    valid_ranges = {start for start, _ in _LEVEL_RANGES}
    if levels is None or step not in {"currentrange", "currentdetails", "targetrange"}:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    if range_start not in valid_ranges:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    await callback.answer()
    if step == "currentrange":
        character_name = next(
            (item["name"] for item in _CALC_CACHE["items"] if str(item["id"]) == character_id),
            character_id,
        )
        await _send_range_prompt(
            callback,
            f"{character_name}\n\nCharacter Level\nSelect the current level range:",
            character_id,
            "current",
            levels,
        )
        return
    if step == "currentdetails":
        await _send_current_details(callback, character_id, range_start, levels)
        return
    await _send_range_prompt(
        callback,
        "Choose the target Character Level range, then set target levels for "
        "the character and each talent:",
        character_id,
        "target",
        levels,
    )


@router.callback_query(lambda query: query.data and query.data.startswith("calccurrent|"))
async def handle_calculate_current_level(callback: types.CallbackQuery):
    payload = await _payload(callback, "calccurrent")
    if payload is None:
        return
    if len(payload) != 5:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    character_id, range_value, field, level_value, state = payload
    levels = _valid_levels(state)
    try:
        range_start, level = int(range_value), int(level_value)
    except ValueError:
        range_start, level = 0, 0
    field_index = next(
        (index for index, (key, _, _) in enumerate(_LEVEL_FIELDS) if key == field),
        None,
    )
    if (levels is None or field_index is None
            or range_start not in {start for start, _ in _LEVEL_RANGES}
            or not (range_start <= level <= min(range_start + 9, 90)
                    if field == "level" else 1 <= level <= 10)):
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    levels[field_index] = level
    await callback.answer()
    await _send_current_details(
        callback, character_id, range_start, levels, edit_in_place=True,
    )


@router.callback_query(lambda query: query.data and query.data.startswith("calcdone|"))
async def handle_calculate_current_done(callback: types.CallbackQuery):
    payload = await _payload(callback, "calcdone")
    if payload is None:
        return
    if len(payload) != 3:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    character_id, range_value, state = payload
    levels = _valid_levels(state)
    try:
        range_start = int(range_value)
    except ValueError:
        range_start = 0
    if levels is None or range_start not in {start for start, _ in _LEVEL_RANGES}:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    if any(level == 0 for level in levels):
        await callback.answer(
            "Choose a current level for all four details first.",
            show_alert=True,
        )
        return
    if not range_start <= levels[0] <= min(range_start + 9, 90):
        await callback.answer(
            "Choose a character level in this range first.",
            show_alert=True,
        )
        return
    await callback.answer()
    if levels[0] == 90:
        await _send_target_details(callback, character_id, 81, levels, list(levels))
        return
    await _send_range_prompt(
        callback,
        "Choose the target Character Level range, then set target levels for "
        "the character and each talent:",
        character_id,
        "target",
        levels,
    )


@router.callback_query(lambda query: query.data and query.data.startswith("ct|"))
async def handle_calculate_target_choice(callback: types.CallbackQuery):
    payload = await _payload(callback, "ct")
    if payload is None:
        return
    if len(payload) != 6:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    (character_id, range_value, current_state, target_state,
     field_code, target_value) = payload
    current_levels = _valid_levels(current_state)
    target_levels = _valid_levels(target_state)
    field_index = next(
        (index for index, code in enumerate(("l", "n", "s", "b"))
         if code == field_code),
        None,
    )
    try:
        range_start, target = int(range_value), int(target_value)
    except ValueError:
        range_start, target = 0, 0
    if (current_levels is None or target_levels is None or field_index is None
            or range_start not in {start for start, _ in _LEVEL_RANGES}
            or any(level == 0 for level in current_levels)
            or not current_levels[field_index] <= target <= (90 if field_index == 0 else 10)
            or (field_index == 0 and target != current_levels[0]
                and not range_start <= target <= min(range_start + 9, 90))):
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    target_levels[field_index] = target
    await callback.answer()
    await _send_target_details(
        callback,
        character_id,
        range_start,
        current_levels,
        target_levels,
        edit_in_place=True,
    )


@router.callback_query(lambda query: query.data and query.data.startswith("ctd|"))
async def handle_calculate_targets_done(callback: types.CallbackQuery):
    payload = await _payload(callback, "ctd")
    if payload is None:
        return
    if len(payload) != 4:
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    character_id, current_state, target_state, range_value = payload
    current_levels = _valid_levels(current_state)
    target_levels = _valid_levels(target_state)
    try:
        range_start = int(range_value)
    except ValueError:
        range_start = 0
    if (current_levels is None or target_levels is None
            or range_start not in {start for start, _ in _LEVEL_RANGES}
            or any(current == 0 or target < current
                   for current, target in zip(current_levels, target_levels))):
        await callback.answer(
            "Target levels cannot be below current levels.",
            show_alert=True,
        )
        return
    if (target_levels[0] != current_levels[0]
            and not range_start <= target_levels[0] <= min(range_start + 9, 90)):
        await callback.answer("This calculator selection is invalid.", show_alert=True)
        return
    if all(current == target for current, target in zip(current_levels, target_levels)):
        await callback.answer(
            "Choose at least one target level above its current level.",
            show_alert=True,
        )
        return
    character = next(
        (item for item in _CALC_CACHE["items"] if str(item["id"]) == character_id),
        None,
    )
    if character is None:
        await callback.answer(
            "Character data expired. Please start /calculate again.",
            show_alert=True,
        )
        return

    key = (
        (callback.message.chat.id, callback.message.message_id)
        if callback.message else None
    )
    if key is not None and key in _CALC_RUNNING:
        await callback.answer("Already calculating...")
        return
    if key is not None:
        _CALC_RUNNING.add(key)

    try:
        await callback.answer()

        # Replace the button screen with a Loading message before calculating.
        if callback.message:
            try:
                await asyncio.to_thread(
                    _edit_rich_markdown_sync,
                    callback.bot.token,
                    callback.message.chat.id,
                    callback.message.message_id,
                    f"# Loading...\n\nCalculating {_md_escape(character['name'])} "
                    "upgrade materials, please wait.",
                )
            except Exception as error:
                logging.debug("Could not show loading message: %s", error)

        markdown = None
        rich_message = None
        try:
            sections = await calculate_materials_split(character, current_levels, target_levels)
            result_text = format_calc_materials(
                sections, character["name"], current_levels, target_levels,
            )
            markdown = build_materials_markdown(
                sections, character["name"], current_levels, target_levels,
            )
        except ValueError as error:
            logging.error("Calculator setup failed: %s", error)
            result_text = f"Could not calculate materials: {error}"
        except RuntimeError as error:
            logging.exception("HoYoLAB material calculation failed")
            result_text = f"HoYoLAB could not calculate these materials: {error}"
        except requests.RequestException:
            logging.exception("HoYoLAB material calculation request failed")
            result_text = (
                "Could not reach HoYoLAB to calculate materials. "
                "Please try again later."
            )

        if markdown and RICH_MESSAGE_AVAILABLE:
            try:
                rich_message = build_materials_rich_message(
                    sections, character["name"], current_levels, target_levels,
                )
            except Exception:
                logging.exception("Could not build rich materials message")

        edited = False
        if (rich_message is not None and callback.message
                and hasattr(callback.message, "answer_rich")):
            try:
                await callback.bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    rich_message=rich_message,
                )
                edited = True
            except Exception as error:
                logging.error("Rich materials edit failed: %s", error)
        if not edited and markdown and callback.message:
            try:
                await asyncio.to_thread(
                    _edit_rich_markdown_sync,
                    callback.bot.token,
                    callback.message.chat.id,
                    callback.message.message_id,
                    markdown,
                )
                edited = True
            except Exception as error:
                logging.error("Rich markdown edit failed: %s", error)
        if not edited:
            await _send_callback_message(callback, result_text)
    finally:
        if key is not None:
            _CALC_RUNNING.discard(key)