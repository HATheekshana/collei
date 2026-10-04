"""Phase-aware endgame countdowns: next opens, current closes."""
from datetime import datetime, timedelta, timezone
from utils.stygian_schedule import ensure_schedule, countdown as stygian_countdown, REGIONS
from utils.banner import ENDGAME_CATEGORIES, _load_banner_data, _format_duration


def next_monthly_start(category, region, now):
    # Official monthly refresh: Abyss 16th, Theatre 1st, 04:00 server time.
    # https://support.hoyoverse.com/hc/en-us/articles/50333950598553
    day = {"abyss": 16, "theatre": 1}[category]
    server_zone = timezone(timedelta(hours=REGIONS[region]))
    local = now.astimezone(server_zone)
    target = local.replace(day=day, hour=4, minute=0, second=0, microsecond=0)
    if target <= local:
        year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
        target = target.replace(year=year, month=month)
    return target.astimezone(timezone.utc)


def get_single_endgame_text(category, now=None, mode="current"):
    if category not in ENDGAME_CATEGORIES:
        return ""
    if mode not in ("current", "next"):
        raise ValueError("Invalid countdown mode")
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if category == "stygian":
        entry = _load_banner_data().get("endgame", {}).get("stygian", {})
        return stygian_countdown(current_time, mode, _format_duration, entry)
    title = ENDGAME_CATEGORIES[category][2]
    lines = [f"🎭 <b>{title}</b>"]
    for region in REGIONS:
        target = next_monthly_start(category, region, current_time)
        label = "Starts in" if mode == "next" else "Ends in"
        lines.append(f"<b>{region}:</b> <code>{label} {_format_duration(target, current_time)}</code>")
    return "\n".join(lines)


def get_endgame_text(now=None, mode="current"):
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return "\n\n".join(get_single_endgame_text(category, current_time, mode)
                         for category in ("abyss", "theatre", "stygian"))
