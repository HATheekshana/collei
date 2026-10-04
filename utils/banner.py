from __future__ import annotations
from utils import storage

import json
import os
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
import requests
from dotenv import load_dotenv

load_dotenv()

BANNER_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "artifacts", "banner_data.json")

# Authenticated (but cookie-free — just a UID) calendar endpoint. Returns per-pool
# start/end timestamps for the *actual* server queried, plus full character lists
# for pools that have been revealed (including `is_invisible` for silhouettes that
# haven't been revealed yet). Requires a real in-game UID; unlike the old public
# torikushiii calendar this is scoped to one server per call.
HOYOLAB_ACT_CALENDAR_URL = (
    "https://sg-act-public-api.hoyolab.com/"
    "event/game_record/genshin/api/act_calendar"
)
SERVER_MAP = {
    "asia": "os_asia",
    "os_asia": "os_asia",

    "eu": "os_euro",
    "os_euro": "os_euro",

    "na": "os_usa",
    "os_usa": "os_usa",
}
# Backward-compat alias — other modules (e.g. utils/endgame.py) import
# CALENDAR_API_URL directly from this file. Points at the new endpoint now.
CALENDAR_API_URL = HOYOLAB_ACT_CALENDAR_URL

# The calendar API returns raw timestamps for whichever server was queried. These
# offsets convert between servers' real-world reset hours so the other two regions'
# times can still be derived from a single query (see _region_times_from_queried_region).
REGION_OFFSETS_SECONDS = {
    "Asia": 0,
    "EU": 7 * 3600,
    "NA": 13 * 3600,
}
_SERVER_KEY_TO_REGION = {
    "asia": "Asia",
    "os_asia": "Asia",

    "eu": "EU",
    "os_euro": "EU",

    "na": "NA",
    "os_usa": "NA",
}

def _empty_region_map() -> dict[str, None]:
    return {region: None for region in REGION_OFFSETS_SECONDS}


# Which activity-list entry backs each endgame category, and where it lives in
# the act_calendar payload. Abyss/Theatre are always present in fixed_act_list
# with real timestamps; Stygian (and other rotating challenges) live in
# act_list and are frequently unscheduled (start/end timestamp "0") between
# rotations.
ENDGAME_CATEGORIES = {
    "abyss": ("fixed_act_list", "Abyssal Moon Spire", "Spiral Abyss"),
    "theatre": ("fixed_act_list", "Imaginarium Theater", "Imaginarium Theater"),
    "stygian": ("act_list", "Stygian Onslaught", "Stygian Onslaught"),
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
    "special_event": {
        "name": None,
        "start": {
            "Asia": None,
            "EU": None,
            "NA": None,
        },
    },
    # Confirmed start and end boundaries for each endgame activity.
    "endgame": {
        category: {"end": _empty_region_map(), "start": _empty_region_map(), "estimated": False}
        for category in ENDGAME_CATEGORIES
    },
}


def _load_banner_data() -> dict[str, Any]:
    return {**DEFAULT_BANNER_DATA, **storage.read("banners", {})}


def _save_banner_data(data: dict[str, Any]) -> None:
    storage.save("banners", data)


def _unix_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _region_times(base_unix_ts: int) -> dict[str, str]:
    return {
        region: _unix_to_iso(base_unix_ts + offset)
        for region, offset in REGION_OFFSETS_SECONDS.items()
    }


def _region_times_from_queried_region(actual_unix_ts: int, queried_region_key: str) -> dict[str, str]:
    """
    Derive all three regions' times from a timestamp that's already real for
    `queried_region_key` (e.g. "Asia"/"EU"/"NA"), by first subtracting that
    region's offset to recover the Asia-baseline instant, then re-applying
    _region_times as before.
    """
    base_unix_ts = actual_unix_ts - REGION_OFFSETS_SECONDS.get(queried_region_key, 0)
    return _region_times(base_unix_ts)


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


def _find_special_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Return the first matching special event (Theater/Abyss/Stygian) from the
    calendar payload's activity lists. Checked against `fixed_act_list` first
    (Abyssal Moon Spire / Imaginarium Theater are always there with real
    start/end timestamps) then `act_list` (Stygian Onslaught and other
    rotating challenges — these frequently have start_timestamp "0" while
    locked, which is treated as "not yet announced" downstream).
    """
    keywords = ("theatre", "theater", "abyss", "stygian")
    for act in [*payload.get("fixed_act_list", []), *payload.get("act_list", [])]:
        name = str(act.get("name") or "").strip()
        if not name or not any(keyword in name.lower() for keyword in keywords):
            continue
        start_ts = int(act.get("start_timestamp") or 0)
        if not start_ts:
            continue
        return {
            "name": name,
            "start": _region_times(start_ts),
        }
    return None


def _compute_endgame_data(
    payload: dict[str, Any], queried_region_key: str, now: datetime
) -> dict[str, Any]:
    """Save confirmed calendar boundaries; evaluate each region at display time."""
    result: dict[str, Any] = {}
    for category, (array_name, entry_name, _title) in ENDGAME_CATEGORIES.items():
        entry = next(
            (e for e in payload.get(array_name, []) if e.get("name") == entry_name), None
        )
        try:
            start_ts = int(entry.get("start_timestamp") or 0) if entry else 0
            end_ts = int(entry.get("end_timestamp") or 0) if entry else 0
        except (TypeError, ValueError):
            start_ts = end_ts = 0
        if start_ts <= 0 or end_ts <= start_ts:
            result[category] = {"end": _empty_region_map(), "start": _empty_region_map(), "estimated": False}
            continue
        # Keep both boundaries. A cached snapshot must remain correct when a
        # region starts or finishes after the last calendar sync.
        result[category] = {
            "start": _region_times_from_queried_region(start_ts, queried_region_key),
            "end": _region_times_from_queried_region(end_ts, queried_region_key),
            "estimated": False,
        }

    return result


def fetch_hoyolab_calendar(uid: str, region: str = "asia") -> dict[str, Any] | None:
    server = SERVER_MAP.get(region.lower())
    if not server:
        raise ValueError(f"Invalid region: {region}")
    payload = {
        "server": server,
        "role_id": str(uid),
    }
    # This endpoint doesn't reliably honor a "lang" field inside the JSON body --
    # it reads locale from the x-rpc-language header and/or a lang= query param,
    # falling back to the account's saved HoYoLAB locale (tied to ltuid/ltoken)
    # when neither is present. That's why setting only payload["lang"] had no
    # effect and results kept coming back in the account's Chinese locale.
    url = f"{HOYOLAB_ACT_CALENDAR_URL}?{urlencode({'lang': 'en-us'})}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://act.hoyolab.com",
        "Referer": "https://act.hoyolab.com/",
        "x-rpc-language": "en-us",
    }

    ltuid = os.getenv("HOYOLAB_LTUID")
    ltoken = os.getenv("HOYOLAB_LTOKEN")
    cookies = {}

    if ltuid and ltoken:
        cookies = {
            "ltuid_v2": ltuid,
            "ltoken_v2": ltoken,
        }
        logging.info(
            "Using HoYoLAB ltuid/ltoken auth cookies (LTUID=%s...)",
            ltuid[:8]
        )
    else:
        logging.warning(
            "HOYOLAB_LTUID or HOYOLAB_LTOKEN not set; "
            "request will fail with retcode=10001"
        )

    try:
        logging.debug(
            "POST %s with payload=%s, cookies=%s",
            url,
            payload,
            list(cookies.keys())
        )
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            cookies=cookies,
            timeout=15,
        )
        logging.info("HoYoLAB HTTP status: %s", response.status_code)
        logging.info("HoYoLAB auth cookies sent: %s", list(cookies.keys()))
        logging.info("HoYoLAB raw response: %s", response.text[:2000])
        logging.warning("NOTE: If still getting retcode=10001, cookies may be expired. Refresh from act.hoyolab.com.")
        response.raise_for_status()
        data = response.json()
        logging.info(
            "HoYoLAB retcode=%s message=%s",
            data.get("retcode"),
            data.get("message"),
        )
        if data.get("retcode") != 0:
            logging.error(
                "HoYoLAB API error: retcode=%s message=%s data=%s",
                data.get("retcode"),
                data.get("message"),
                data.get("data"),
            )
            return None
        logging.info("HoYoLAB API request successful")
        logging.info("HoYoLAB response keys: %s", list(data.keys()))
        return data.get("data")
    except requests.RequestException as e:
        logging.error("HoYoLAB request failed: %s", e)
        return None
    except ValueError as e:
        logging.error("HoYoLAB returned invalid JSON: %s", e)
        return None


def _pool_to_banner(pool: dict[str, Any]) -> dict[str, Any] | None:
    avatars = [
        a
        for a in pool.get("avatars", [])
        if not a.get("is_invisible") and a.get("name")
    ]

    if not avatars:
        return None

    logging.info(
        "HoYoLAB pool: %s",
        {
            "pool_id": pool.get("pool_id"),
            "pool_name": pool.get("pool_name"),
            "pool_type": pool.get("pool_type"),
            "start_timestamp": pool.get("start_timestamp"),
            "end_timestamp": pool.get("end_timestamp"),
            "countdown_seconds": pool.get("countdown_seconds"),
            "avatar_count": len(avatars),
        }
    )

    start_ts = pool.get("start_timestamp")
    end_ts = pool.get("end_timestamp")
    if not start_ts or not end_ts:
        logging.warning(
            "Pool has no timestamps: pool_id=%s pool_name=%s keys=%s",
            pool.get("pool_id"),
            pool.get("pool_name"),
            list(pool.keys()),
        )
        return None

    return {
        "pool_id": pool.get("pool_id"),
        "title": pool.get("pool_name") or "",
        "characters": [
            {
                "name": a.get("name"),
                "icon": a.get("icon"),
                "rarity": a.get("rarity"),
            }
            for a in avatars
        ],
        "start_time": int(start_ts),
        "end_time": int(end_ts),
        "countdown_seconds": pool.get("countdown_seconds"),
    }

async def fetch_banner_data_from_hoyolab(uid: str, region: str = "asia") -> dict[str, Any] | None:
    """
    Fetch current & upcoming character banner data.

    This used to call a public, cookie-free calendar API that only ever returned a
    single Asia-server timestamp for the *whole game*, with no notion of which UID
    was asking. It's replaced with HoYoLAB's authenticated act_calendar endpoint,
    which is scoped to a real UID + server and returns actual per-pool character
    lists (including whether a character is still an unrevealed silhouette via
    `is_invisible`), rather than one flattened calendar entry per banner.

    NOTE: unlike the previous implementation, this requires a real in-game UID
    and a specific server ("asia"/"eu"/"na") — it can no longer be called with
    no arguments. The other two regions' times are still derived from the
    queried server's real timestamps via REGION_OFFSETS_SECONDS, same as before.

    Returns:
        Updated banner data dict or None if fetch fails
    """
    payload = fetch_hoyolab_calendar(uid, region)

    if payload is None:
        return None

    logging.info(
        "HoYoLAB calendar keys: %s",
        list(payload.keys())
    )

    logging.info(
        "HoYoLAB avatar pools: %s",
        len(payload.get("avatar_card_pool_list", []))
    )

    logging.info(
        "HoYoLAB mixed pools: %s",
        len(payload.get("mixed_card_pool_list", []))
    )

    queried_region_key = _SERVER_KEY_TO_REGION.get(region.lower(), "Asia")

    all_pools = [*payload.get("avatar_card_pool_list", []), *payload.get("mixed_card_pool_list", [])]

    character_banners = [b for b in (_pool_to_banner(p) for p in all_pools) if b]

    if not character_banners:
        logging.warning("No revealed character banners found in act_calendar response")
        return None

    now = datetime.now(timezone.utc)

    def _dt(ts: int) -> datetime:
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    current_banners = [
        b for b in character_banners
        if _dt(b["start_time"]) <= now <= _dt(b["end_time"])
    ]

    # Timing for "next banner starts in" is intentionally computed from ALL pool
    # entries (not just ones with revealed characters) — HoYoverse sometimes lists
    # the next pool's start/end time before revealing who's actually in it. If we
    # only looked at character_banners here, /next would keep showing stale
    # placeholder countdown data until characters leaked.
    future_all_pools = sorted(
        (
            p for p in all_pools
            if p.get("start_timestamp") and int(p["start_timestamp"]) > 0 and _dt(int(p["start_timestamp"])) > now
        ),
        key=lambda p: int(p["start_timestamp"]),
    )
    next_all_pools: list[dict] = []
    if future_all_pools:
        earliest_start = future_all_pools[0]["start_timestamp"]
        next_all_pools = [p for p in future_all_pools if p["start_timestamp"] == earliest_start]

    next_char_banners = [b for b in (_pool_to_banner(p) for p in next_all_pools) if b]

    current_characters, current_icons = _names_and_icons(current_banners)
    next_characters, next_icons = _names_and_icons(next_char_banners)

    banner_data = _load_banner_data()

    if current_banners:
        banner_data["current_end"] = _region_times_from_queried_region(
            int(current_banners[0]["end_time"]), queried_region_key
        )

    # Always reflect what the API actually says about the next banner —
    # including overwriting it to empty/TBA when the API has nothing right
    # now. Previously this only updated when a future banner window was
    # found, which meant a stale value set earlier via /bupdate (or from an
    # older sync) would keep showing indefinitely. The API is now the single
    # source of truth for "next banner" data.
    if next_all_pools:
        banner_data["next_start"] = _region_times_from_queried_region(
            int(next_all_pools[0]["start_timestamp"]), queried_region_key
        )
    else:
        banner_data["next_start"] = banner_data.get("current_end", {"Asia": None, "EU": None, "NA": None})
    banner_data["next_characters"] = next_characters
    banner_data["next_icons"] = next_icons

    special_event = _find_special_event(payload)
    if special_event:
        banner_data["special_event"] = special_event
    else:
        banner_data["special_event"] = {
            "name": None,
            "start": {region: None for region in REGION_OFFSETS_SECONDS},
        }

    banner_data["endgame"] = _compute_endgame_data(payload, queried_region_key, now)

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
    special_event: dict[str, Any] | None = None,
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
    if special_event is not None:
        data["special_event"] = special_event

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
        lines = [f"<b>{region_key}:</b> <code>{_format_duration(target, current_time)}</code>"]
        return "\n".join(lines)

    return get_banner_text(mode=mode, now=current_time)