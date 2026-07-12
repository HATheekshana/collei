from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone
from typing import Any
import requests

BANNER_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "artifacts", "banner_data.json")

# Public, no-auth-required calendar API (see https://github.com/torikushiii/hoyoverse-api).
# The old code called https://hoyolab.com/genshin/h5/traveler_contain/calendar, which is a
# *frontend page*, not an API endpoint — it returns HTML, so response.json() always raised
# and /bsync silently reported failure. This endpoint returns real JSON and needs no cookies.
CALENDAR_API_URL = "https://api.ennead.cc/mihoyo/genshin/calendar"

# The calendar API only gives a single UTC end/start timestamp (the Asia server value).
# Genshin's three server groups reset at different real-world hours; these offsets convert
# the Asia timestamp into the other regions' local reset times.
REGION_OFFSETS_SECONDS = {
    "Asia": 0,
    "EU": 7 * 3600,
    "NA": 13 * 3600,
}

DEFAULT_BANNER_DATA = {
    "current_end": {
        "Asia": "2026-05-19T07:00:00Z",
        "EU": "2026-05-19T14:00:00Z",
        "NA": "2026-05-19T20:00:00Z",
    },
    # None (not a stale hardcoded date) until we actually know the next banner's
    # start time — a fixed placeholder date always ends up in the past, which
    # made /next show a misleading "Live! / Finished" instead of a real
    # countdown or an honest "not yet announced".
    "next_start": {
        "Asia": None,
        "EU": None,
        "NA": None,
    },
    "current_characters": ["Character 1", "Character 2"],
    "next_characters": [],
    "current_icons": [],
    "next_icons": [],
}


def _load_banner_data() -> dict[str, Any]:
    if os.path.exists(BANNER_DATA_FILE):
        try:
            with open(BANNER_DATA_FILE, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
                if isinstance(loaded, dict):
                    return {**DEFAULT_BANNER_DATA, **loaded}
        except Exception:
            pass
    return DEFAULT_BANNER_DATA.copy()


def _save_banner_data(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(BANNER_DATA_FILE), exist_ok=True)
    with open(BANNER_DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _unix_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _region_times(base_unix_ts: int) -> dict[str, str]:
    return {
        region: _unix_to_iso(base_unix_ts + offset)
        for region, offset in REGION_OFFSETS_SECONDS.items()
    }


def _rarity_value(rarity) -> int:
    """Coerce a rarity field (int, numeric string, or 'S'/'A'/'B' style grade) to an int."""
    try:
        return int(rarity)
    except (TypeError, ValueError):
        return {"S": 5, "A": 4, "B": 3}.get(str(rarity).strip().upper(), 0)


def _names_and_icons(banners: list[dict]) -> tuple[list[str], list[str]]:
    """
    Collect character names (every featured character, 5-star first — for the
    text list) and icon URLs of 5-star characters ONLY (for the image
    slideshow — 4-star icons are intentionally excluded there).
    """
    names: list[str] = []
    icons: list[str] = []
    for banner in banners:
        chars = sorted(
            banner.get("characters", []),
            key=lambda c: -_rarity_value(c.get("rarity")),
        )
        for c in chars:
            name = c.get("name")
            if not name or name in names:
                continue
            names.append(name)
            icon = c.get("icon")
            if icon and _rarity_value(c.get("rarity")) == 5:
                icons.append(icon)
    return names, icons


async def fetch_banner_data_from_hoyolab(cookies_str: str | None = None) -> dict[str, Any] | None:
    """
    Fetch current & upcoming character banner data.

    This used to call https://hoyolab.com/genshin/h5/traveler_contain/calendar with
    HoYoLab account cookies. That URL is a browser page, not an API — it returns HTML,
    so `response.json()` always threw and /bsync failed 100% of the time regardless of
    cookies. It's replaced with a public, cookie-free calendar API that returns real JSON
    with proper banner/character/icon data.

    The `cookies_str` parameter is kept for backwards compatibility but is unused.

    Returns:
        Updated banner data dict or None if fetch fails
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ColleiBot/1.0; +banner-sync)",
            "Accept": "application/json",
        }
        response = requests.get(CALENDAR_API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch Genshin calendar: {e}")
        return None
    except ValueError as e:
        logging.error(f"Invalid JSON response from calendar API: {e}")
        return None

    banners = payload.get("banners", [])
    # Only banners that actually feature characters (skips weapon-only banners),
    # this is what caused "wrong" banner text before — the old code grabbed the
    # `title` of *any* calendar entry (events included), not the real gacha banner.
    character_banners = [b for b in banners if b.get("characters")]

    if not character_banners:
        logging.warning("No character banners found in calendar response")
        return None

    now = datetime.now(timezone.utc)

    def _dt(ts) -> datetime:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)

    current_banners = [
        b for b in character_banners
        if _dt(b["start_time"]) <= now <= _dt(b["end_time"])
    ]

    # Timing for "next banner starts in" is intentionally computed from ALL
    # banner entries (not just ones with revealed characters) — HoYoverse
    # sometimes lists the next banner's start/end time before announcing who's
    # actually in it. If we only looked at character_banners here, /next would
    # keep showing stale placeholder countdown data until characters leaked.
    future_all_banners = sorted(
        (b for b in banners if b.get("start_time") and _dt(b["start_time"]) > now),
        key=lambda b: b["start_time"],
    )
    next_all_banners: list[dict] = []
    if future_all_banners:
        earliest_start = future_all_banners[0]["start_time"]
        next_all_banners = [b for b in future_all_banners if b["start_time"] == earliest_start]

    next_char_banners = [b for b in next_all_banners if b.get("characters")]

    current_characters, current_icons = _names_and_icons(current_banners)
    next_characters, next_icons = _names_and_icons(next_char_banners)

    banner_data = _load_banner_data()

    if current_banners:
        banner_data["current_end"] = _region_times(int(current_banners[0]["end_time"]))

    # Always reflect what the API actually says about the next banner —
    # including overwriting it to empty/TBA when the API has nothing right
    # now. Previously this only updated when a future banner window was
    # found, which meant a stale value set earlier via /bupdate (or from an
    # older sync) would keep showing indefinitely. The API is now the single
    # source of truth for "next banner" data.
    if next_all_banners:
        banner_data["next_start"] = _region_times(int(next_all_banners[0]["start_time"]))
    else:
        banner_data["next_start"] = banner_data.get("current_end", {"Asia": None, "EU": None, "NA": None})
    banner_data["next_characters"] = next_characters
    banner_data["next_icons"] = next_icons

    if current_characters:
        banner_data["current_characters"] = current_characters
        banner_data["current_icons"] = current_icons

    _save_banner_data(banner_data)
    logging.info(
        f"Banner data synced: current={current_characters}, next={next_characters or 'TBA'}"
    )
    return banner_data


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_duration(target: datetime, now: datetime, not_started_label: str = "Live! / Finished") -> str:
    diff = target - now
    if diff.total_seconds() <= 0:
        return not_started_label

    days = diff.days
    hours, rem = divmod(diff.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m"


def format_banner_countdown(target: datetime, region: str, now: datetime | None = None) -> str:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    target_utc = target.astimezone(timezone.utc)
    delta = target_utc - current_time
    if delta.total_seconds() <= 0:
        return "Live! / Finished"

    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{region}: {days}d {hours}h {minutes}m"


def get_banner_text(mode: str = "current", now: datetime | None = None) -> str:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    data = _load_banner_data()
    if mode == "current":
        title = "⏳ <b>CURRENT BANNER ENDS IN:</b>"
        target_map = data.get("current_end", {})
    else:
        title = "🚀 <b>NEXT BANNER STARTS IN:</b>"
        target_map = data.get("next_start", {})

    lines = [title, "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"]
    not_started_label = "Not yet announced" if mode == "next" else "Live! / Finished"
    has_real_time = False
    for region, target_value in target_map.items():
        if not target_value:
            lines.append(f"<b>{region}:</b> <code>Not yet announced</code>")
            continue
        has_real_time = True
        target = _parse_datetime(target_value)
        lines.append(f"<b>{region}:</b> <code>{_format_duration(target, current_time, not_started_label)}</code>")

    characters = data.get("current_characters" if mode == "current" else "next_characters", [])
    if characters:
        lines.append("")
        lines.append("<b>Characters:</b>")
        lines.extend(f"• {name}" for name in characters)
    elif mode == "next" and has_real_time:
        lines.append("")
        lines.append("<b>Characters:</b> TBA (not yet revealed)")

    return "\n".join(lines)


def get_banner_icons(mode: str = "current") -> list[str]:
    """Character splash/icon URLs for the current or next banner, for rich media replies."""
    data = _load_banner_data()
    key = "current_icons" if mode == "current" else "next_icons"
    return data.get(key, [])


def update_banner_data(
    current_characters: list[str] | None = None,
    next_characters: list[str] | None = None,
    current_end: dict[str, str] | None = None,
    next_start: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = _load_banner_data()
    if current_characters is not None:
        data["current_characters"] = current_characters
    if next_characters is not None:
        data["next_characters"] = next_characters
    if current_end is not None:
        data["current_end"] = current_end
    if next_start is not None:
        data["next_start"] = next_start

    if data.get("current_end") and not data.get("next_start"):
        data["next_start"] = data["current_end"].copy()
    elif data.get("current_end") and any(value is None for value in data.get("next_start", {}).values()):
        data["next_start"] = data["current_end"].copy()

    _save_banner_data(data)
    return data


def get_banner_countdown_text(region: str | None = None, mode: str = "current", now: datetime | None = None) -> str:
    """
    Return a regional countdown for the current or next banner.

    When `mode == "current"`, this returns the current banner end time.
    When `mode == "next"`, this returns the next banner start time.
    """
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if region:
        normalized = (region or "").strip().lower()
        if normalized not in {"na", "eu", "asia", "northamerica", "america", "americas", "europe", "europa", "apac", "eastasia"}:
            usage_command = "/current" if mode == "current" else "/next"
            return f"Usage: {usage_command} [na|eu|asia]"
        data = _load_banner_data()
        target_map = data.get("current_end" if mode == "current" else "next_start", {})
        region_key = "NA" if normalized in {"na", "northamerica", "america", "americas"} else "EU" if normalized in {"eu", "europe", "europa"} else "Asia"
        target_value = target_map.get(region_key)
        if not target_value:
            return f"<b>{region_key}:</b> <code>Not yet announced</code>"
        target = _parse_datetime(target_value)
        return f"<b>{region_key}:</b> <code>{_format_duration(target, current_time)}</code>"

    return get_banner_text(mode=mode, now=current_time)
