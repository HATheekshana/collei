"""Use the card renderer's cycle schedule for Stygian countdowns."""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

REGIONS = {"Asia": 8, "EU": 1, "NA": -5}
_schedule = {}
_retry_at = 0.0
_lock = asyncio.Lock()

# Closing of the playable event, NOT the leyline cycle boundary.
# Official event notice: https://www.hoyolab.com/article/46329018
# Keyed to this cycle only; never applied to subsequent versions.
EVENT_CLOSES = {"5269011": "2026-09-22 03:59:59"}


def boundary(value, region):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Unzoned game schedule strings are server wall-clock times. Explicit
        # offsets, when provided by the source, already identify an instant.
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone(timedelta(hours=REGIONS[region])))
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def windows(data, region):
    result = []
    for identity, row in data.items():
        if not isinstance(row, dict):
            continue
        start = boundary(row.get("live_begin") or row.get("begin"), region)
        end = boundary(row.get("live_end") or row.get("end"), region)
        if start and end and end > start:
            result.append((start, end, str(identity)))
    return sorted(result)


def select(data, region, now, mode):
    periods = windows(data, region)
    if mode == "next":
        return next((row for row in periods if row[0] > now), None)
    return next((row for row in periods if row[0] <= now < row[1]), None)


def _load():
    import stygian
    # Existing renderer fetches its configured leyline.json and uses its disk
    # cache on network failure. Catch its CLI-style exit at the bot boundary.
    try:
        return stygian.fetch_leyline_schedule()
    except SystemExit as error:
        raise RuntimeError("Stygian schedule could not be loaded") from error


async def ensure_schedule():
    global _schedule, _retry_at
    async with _lock:
        if time.monotonic() < _retry_at:
            return
        try:
            data = await asyncio.to_thread(_load)
            if not isinstance(data, dict) or not windows(data, "Asia"):
                raise ValueError("Invalid Stygian schedule")
            _schedule = data
            _retry_at = time.monotonic() + 3600
        except Exception as error:
            logging.warning("Stygian schedule refresh failed: %s", type(error).__name__)
            _retry_at = time.monotonic() + 300


def event_close(row, region, entry):
    start, cycle_end, identity = row
    if identity in EVENT_CLOSES:
        return boundary(EVENT_CLOSES[identity], region)
    if entry and not entry.get("estimated"):
        # HoYoLAB calendar timestamps are zoned UTC instants, independent of
        # the raw dataset's administrative cycle boundary.
        end = boundary((entry.get("end") or {}).get(region), region)
        opened = boundary((entry.get("start") or {}).get(region), region)
        if end and start < end <= cycle_end and (opened is None or start <= opened < cycle_end):
            return end
    return None


def countdown(now, mode, format_duration, calendar_entry=None):
    lines = ["🎭 <b>Stygian Onslaught</b>"]
    for region in REGIONS:
        row = select(_schedule, region, now, mode)
        if row and mode == "next":
            text = "Starts in " + format_duration(row[0], now)
        elif row:
            end = event_close(row, region, calendar_entry)
            if end and now < end:
                text = "Ends in " + format_duration(end, now)
            elif end:
                text = "Ended · " + end.astimezone(timezone(timedelta(hours=REGIONS[region]))).strftime("%d %b %H:%M server time")
            else:
                text = "Event closing time needs a calendar refresh (/bsync)"
        elif mode == "current" and select(_schedule, region, now, "next"):
            text = "Not active · use /next for the start time"
        else:
            # Never replace a fetch failure or outdated dataset with a made-up
            # countdown, or call a published-but-unavailable schedule unannounced.
            text = "Schedule unavailable — refresh failed or cached dates are outdated"
        lines.append(f"<b>{region}:</b> <code>{text}</code>")
    return "\n".join(lines)
