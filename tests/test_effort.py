from datetime import datetime
from zoneinfo import ZoneInfo

from paperless_nc_import.effort import compute_start_datetime, parse_effort


def test_parse_hours():
    spec = parse_effort("3h")
    assert spec is not None
    assert spec.unit == "hours"
    assert spec.amount == 3


def test_workdays_skip_weekend():
    due = datetime(2026, 6, 15, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))  # Monday
    start = compute_start_datetime(due, parse_effort("1d"), "")
    assert start is not None
    assert start.date().isoformat() == "2026-06-12"  # Friday


def test_calendar_days():
    due = datetime(2026, 6, 15, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    start = compute_start_datetime(due, parse_effort("2kt"), "")
    assert start is not None
    assert start.date().isoformat() == "2026-06-13"


def test_hours_preserve_day_math():
    due = datetime(2026, 6, 15, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    start = compute_start_datetime(due, parse_effort("3h"), "")
    assert start is not None
    assert start.isoformat() == "2026-06-15T06:00:00+02:00"
