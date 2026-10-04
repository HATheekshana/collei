"""
utils/cycle_state.py
=====================

Generic current/next id-cycling state machine for the three special-media
categories (abyss, theatre, stygian), driving /nabyss /ntheatre /nstygian
(advance) and /pabyss /ptheatre /pstygian (retreat).

State file (CYCLE_STATE_FILE, e.g. cycle_state.json), same one-small-JSON-
file pattern as banner_data.json:

    {
      "abyss":   {"current": 122,     "next": 123},
      "theatre": {"current": 28,      "next": null},
      "stygian": {"current": 5269010, "next": 5269011}
    }

Id math is category-agnostic: every category is just a sequential integer
id (int(id) +/- 1) -- stygian's ids just happen to look bigger.

This module owns the state file AND drives image generation: it calls into
the category script's own update_core_data() / fetch_<category>() /
fetch_<category>_schedule() / build_card(), publishes the rendered PNG to
Telegram (+ optionally imgbb) to get a file_id, then stores/relabels
entries in special_media.json via utils.special_media's public API.
It never regenerates a card that's simply moving between the current/next
slots -- only a newly revealed id gets an actual build_card() call.

Failure handling: on advance, if the *newly revealed* next id isn't
published upstream yet, the category script's fetch_* raises SystemExit.
We generate that new card BEFORE mutating any stored state, so a failure
there leaves current/next exactly as they were -- no half-applied shift.

ASSUMPTION: abyss.py / theatre.py / stygian.py are importable at the repo
root as `abyss`, `theatre`, `stygian` (matching the filenames you shared).
If they actually live under a subpackage (e.g. scripts.abyss), update the
three imports below accordingly -- nothing else in this file needs to change.
"""

from __future__ import annotations
from utils import storage

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

from aiogram import Bot
from aiogram.types import FSInputFile

from data.config import CYCLE_STATE_FILE, MEDIA_CHANNEL
from utils.special_media import (
    CATEGORIES,
    LABELS,
    get_media,
    load_special_media,
    save_special_media,
)

import abyss
import theatre
import stygian


# ---------------------------------------------------------------------------
# Per-category wiring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryConfig:
    module: object
    fetch: Callable[[int], str]             # fetch_<category>(num) -> cache path; raises SystemExit if unavailable & uncached
    fetch_schedule: Callable[[], dict]       # fetch_<category>_schedule()
    build: Callable[[int], "object"]         # build_card(num) -> PIL.Image (bound with any extra args already applied)
    out_name: Callable[[int], str]           # output filename for this id, under module.OUTPUT_DIR


CATEGORY_CONFIGS: dict[str, CategoryConfig] = {
    "abyss": CategoryConfig(
        module=abyss,
        fetch=abyss.fetch_tower,
        fetch_schedule=abyss.fetch_tower_schedule,
        build=abyss.build_card,
        out_name=lambda num: f"abyss_cycle{num}.png",
    ),
    "theatre": CategoryConfig(
        module=theatre,
        fetch=theatre.fetch_rolecombat,
        fetch_schedule=theatre.fetch_rolecombat_schedule,
        # Difficulty isn't part of this state model -- always render the
        # top (default) tier, same default main() uses.
        build=lambda num: theatre.build_card(num, "5"),
        out_name=lambda num: f"theater_act{num}_d5.png",
    ),
    "stygian": CategoryConfig(
        module=stygian,
        fetch=stygian.fetch_leyline,
        fetch_schedule=stygian.fetch_leyline_schedule,
        build=stygian.build_card,
        out_name=lambda num: f"stygian_{num}.png",
    ),
}


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

def _default_state() -> dict:
    return {cat: {"current": None, "next": None} for cat in CATEGORIES}


def load_cycle_state() -> dict:
    return {**_default_state(), **storage.read("cycles", {})}


def save_cycle_state(data: dict) -> None:
    storage.save("cycles", data)


def seed_current(category: str, current_id: int) -> None:
    """One-time admin bootstrap: set a category's starting `current` id
    (with no `next` yet) before /n<category> is ever run. Not exposed as a
    bot command by default -- edit cycle_state.json directly, or call this
    from a shell/console if you want a /setcurrent command later."""
    state = load_cycle_state()
    state[category] = {"current": int(current_id), "next": None}
    save_cycle_state(state)


def _step(num: int, delta: int) -> int:
    """Category-agnostic sequential id math -- the same int(id) +/- 1 works
    for abyss/theatre's small ints and stygian's 7-digit ids."""
    return int(num) + delta


# ---------------------------------------------------------------------------
# special_media.json plumbing (relabeling current<->next slots)
# ---------------------------------------------------------------------------

def _media_key(phase: str, category: str) -> str:
    # NOTE: must match utils.special_media._key()'s "phase:category" format.
    return f"{phase}:{category}"


def _set_media(phase: str, category: str, entries: list[dict]) -> None:
    """Overwrite the stored image list for phase+category in one shot --
    used both to relabel current<->next (move an already-rendered card
    between slots) and to drop a slot's contents entirely (pass [])."""
    data = load_special_media()
    data[_media_key(phase, category)] = entries
    save_special_media(data)


# ---------------------------------------------------------------------------
# Card generation (blocking -- run via asyncio.to_thread) + publishing
# ---------------------------------------------------------------------------

class CardNotAvailable(Exception):
    """The upstream id isn't published yet -- the category script's fetch_*
    hit a 404/etc. with nothing cached, and raised SystemExit."""


def _generate_card_sync(category: str, num: int):
    """Blocking: refresh core data, fetch this id's data + the schedule,
    then render the card. Raises CardNotAvailable if the id isn't published
    yet. Returns the saved output path."""
    cfg = CATEGORY_CONFIGS[category]
    try:
        cfg.fetch(num)
        cfg.module.update_core_data()
        cfg.fetch_schedule()
        card = cfg.build(num)
    except SystemExit as e:
        raise CardNotAvailable(str(e)) from e

    out_path = os.path.join(cfg.module.OUTPUT_DIR, cfg.out_name(num))
    card.save(out_path)
    return out_path


async def _publish_card(bot: Bot, category: str, phase: str, num: int, out_path: str) -> dict:
    """Send the rendered PNG to MEDIA_CHANNEL, try an imgbb upload too (best
    effort, same as the manual /add<category> flow), and return a
    special_media-style entry: {"file_id": ..., "image_url"?: ...}."""
    label = LABELS.get(category, category.title())
    phase_label = "Next" if phase == "next" else "Current"

    sent = await bot.send_photo(
        chat_id=MEDIA_CHANNEL,
        photo=FSInputFile(out_path),
        caption=f"{phase_label} {label} record image ({num})",
    )
    file_id = sent.photo[-1].file_id

    image_url = None
    try:
        from utils.imgbb import upload_file_by_telegram_download, ImgBBUploadError
        try:
            image_url = await upload_file_by_telegram_download(
                bot, file_id, filename=f"{phase}_{category}_{num}.jpg",
            )
        except ImgBBUploadError as e:
            logging.warning(
                "imgbb upload failed for %s %s %s (will use Telegram fallback): %s",
                phase, category, num, e,
            )
    except Exception as e:
        logging.warning("Error with imgbb upload for %s %s %s: %s", phase, category, num, e)

    entry = {"file_id": file_id}
    if image_url:
        entry["image_url"] = image_url
    return entry


# ---------------------------------------------------------------------------
# Advance / retreat
# ---------------------------------------------------------------------------

@dataclass
class ShiftResult:
    ok: bool
    message: str
    old_current: int | None = None
    old_next: int | None = None
    new_current: int | None = None
    new_next: int | None = None


async def advance(bot: Bot, category: str) -> ShiftResult:
    """/nabyss /ntheatre /nstygian.

    Case A (bootstrap, next is empty): generate current+1, store as next,
    current stays put.

    Case B (rollover, next already exists): the new next (new_current + 1)
    is generated FIRST -- only once that succeeds do we drop the old
    current, promote next -> current (relabel, no regenerate), and store
    the freshly generated card as the new next.
    """
    state = load_cycle_state()
    rec = state[category]
    current, next_ = rec["current"], rec["next"]

    if current is None:
        return ShiftResult(False, f"No starting id set for {category} yet -- seed cycle_state.json first.")

    if next_ is None:
        # Case A -- bootstrap.
        new_next = _step(current, 1)
        try:
            out_path = await asyncio.to_thread(_generate_card_sync, category, new_next)
        except CardNotAvailable as e:
            return ShiftResult(False, f"Could not generate next id {new_next}: {e}")

        entry = await _publish_card(bot, category, "next", new_next, out_path)
        _set_media("next", category, [entry])

        rec["next"] = new_next
        save_cycle_state(state)
        return ShiftResult(True, "bootstrapped next", current, None, current, new_next)

    # Case B -- rollover.
    new_current = next_
    new_next = _step(new_current, 1)
    try:
        out_path = await asyncio.to_thread(_generate_card_sync, category, new_next)
    except CardNotAvailable as e:
        return ShiftResult(False, f"Could not generate next id {new_next}: {e}")

    entry = await _publish_card(bot, category, "next", new_next, out_path)

    # Generation succeeded -- now apply the whole relabel atomically.
    promoted_entries = get_media("next", category)   # already-rendered card for new_current
    _set_media("current", category, promoted_entries)  # relabel next -> current (old current dropped)
    _set_media("next", category, [entry])               # newly generated card

    rec["current"] = new_current
    rec["next"] = new_next
    save_cycle_state(state)
    return ShiftResult(True, "rolled over", current, next_, new_current, new_next)


async def retreat(bot: Bot, category: str) -> ShiftResult:
    """/pabyss /ptheatre /pstygian -- exact inverse of the rollover branch.

    new current = current - 1 (regenerated -- the old copy was deleted on
    whichever /n<category> got us here). Old current demotes back into
    next (relabel, no regenerate); whatever was previously in next is
    discarded, same as an old current is discarded on rollover.
    """
    state = load_cycle_state()
    rec = state[category]
    current, next_ = rec["current"], rec["next"]

    if current is None:
        return ShiftResult(False, f"No starting id set for {category} yet -- seed cycle_state.json first.")

    new_current = _step(current, -1)
    try:
        out_path = await asyncio.to_thread(_generate_card_sync, category, new_current)
    except CardNotAvailable as e:
        return ShiftResult(False, f"Could not generate previous id {new_current}: {e}")

    entry = await _publish_card(bot, category, "current", new_current, out_path)

    # Capture the old current's media BEFORE overwriting anything.
    demoted_entries = get_media("current", category)
    _set_media("next", category, demoted_entries)   # relabel old current -> next
    _set_media("current", category, [entry])          # newly generated card

    rec["current"] = new_current
    rec["next"] = current
    save_cycle_state(state)
    return ShiftResult(True, "retreated", current, next_, new_current, current)
