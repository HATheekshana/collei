import difflib
import re
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helper import normalize_name
from utils.artifacts import find_artifact_info
from utils.helper import find_character_files, find_artifact_files
from data.search_items import SEARCH_ITEMS


def _normalize_query(value: str) -> str:
    return normalize_name(value or "")


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (value or "").lower())


def _matches_all_tokens(query_tokens: list[str], item_tokens: set[str]) -> bool:
    return all(
        any(qt == token or qt in token or token.startswith(qt) for token in item_tokens)
        for qt in query_tokens
    )


def find_search_matches(query: str, max_results: int = 8) -> list[str]:
    query_norm = _normalize_query(query)
    query_tokens = _tokenize(query)
    if not query_norm or not query_tokens:
        return []

    exact_matches = []
    token_matches = []
    prefix_matches = []
    contains_matches = []
    fuzzy_candidates = []

    for key, display_name in SEARCH_ITEMS.items():
        key_norm = _normalize_query(key)
        display_norm = _normalize_query(display_name)
        key_tokens = _tokenize(key)
        display_tokens = _tokenize(display_name)
        all_tokens = set(key_tokens + display_tokens)

        if key_norm == query_norm or display_norm == query_norm:
            exact_matches.append((0, key))
            continue

        if query_tokens == key_tokens or query_tokens == display_tokens:
            token_matches.append((0, key))
            continue

        if _matches_all_tokens(query_tokens, all_tokens):
            token_matches.append((1, key))
            continue

        if key_norm.startswith(query_norm) or display_norm.startswith(query_norm):
            prefix_matches.append((2, key))
            continue

        if any(qt in key_norm or qt in display_norm for qt in query_tokens):
            contains_matches.append((3, key))
            continue

        score = max(
            difflib.SequenceMatcher(None, query_norm, key_norm).ratio(),
            difflib.SequenceMatcher(None, query_norm, display_norm).ratio(),
        )
        if score > 0.55:
            fuzzy_candidates.append((score, key))

    if exact_matches:
        return [k for _, k in exact_matches][:max_results]

    ordered_results = []
    seen = set()

    for score, key in token_matches + prefix_matches + contains_matches:
        if key not in seen:
            seen.add(key)
            ordered_results.append((score, key))
            if len(ordered_results) >= max_results:
                break

    if len(ordered_results) < max_results:
        fuzzy_candidates.sort(key=lambda item: (-item[0], item[1]))
        for _, key in fuzzy_candidates:
            if key not in seen:
                seen.add(key)
                ordered_results.append((4, key))
                if len(ordered_results) >= max_results:
                    break

    return [key for _, key in ordered_results][:max_results]


def render_search_keyboard(keys: list[str], user_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    row = []

    for idx, key in enumerate(keys):
        label = SEARCH_ITEMS.get(key, key.title())
        button = InlineKeyboardButton(
            text=label,
            callback_data=f"search|{user_id}|{key}",
        )
        row.append(button)

        if len(row) >= 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def send_search_result(message: types.Message, key: str):
    from handlers.media import send_rich_slideshow
    
    artifact_info = find_artifact_info(key)
    artifact_files = find_artifact_files(key)
    character_files = find_character_files(key)

    if artifact_info or artifact_files:
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
            return

    if character_files:
        CHUNK_SIZE = 50
        caption = SEARCH_ITEMS.get(key, key.title())
        for i in range(0, len(character_files), CHUNK_SIZE):
            chunk = character_files[i:i + CHUNK_SIZE]
            chunk_caption = caption if i == 0 else None
            try:
                await send_rich_slideshow(message, chunk, caption=chunk_caption)
            except Exception:
                pass
        return

    await message.reply(f"No files found for {key.title()}.")
