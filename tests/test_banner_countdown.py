from datetime import datetime, timedelta, timezone

from utils.banner import format_banner_countdown


def test_format_banner_countdown_for_na_region():
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    target = now + timedelta(days=3, hours=5, minutes=12)
    text = format_banner_countdown(target, region="NA", now=now)

    assert "NA" in text
    assert "3d 5h 12m" in text


def test_format_banner_countdown_for_eu_region():
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    target = now + timedelta(days=1, hours=2, minutes=3)
    text = format_banner_countdown(target, region="EU", now=now)

    assert "EU" in text
    assert "1d 2h 3m" in text
