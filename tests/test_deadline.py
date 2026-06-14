from datetime import date

from paperless_nc_import.deadline import DeadlineMode, calculate_deadline, add_calendar_months


def test_calendar_month_clamps_to_month_end():
    assert add_calendar_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_calendar_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_bgb_event_month_deadline_uses_corresponding_day():
    result = calculate_deadline(date(2026, 1, 31), 1, "Monate", DeadlineMode.BGB_EVENT)
    assert result.value == date(2026, 2, 28)


def test_bgb_start_month_deadline_ends_previous_day():
    result = calculate_deadline(date(2026, 1, 1), 1, "Monate", DeadlineMode.BGB_START)
    assert result.value == date(2026, 1, 31)


def test_bgb_start_week_deadline_ends_previous_day():
    result = calculate_deadline(date(2026, 6, 1), 1, "Wochen", DeadlineMode.BGB_START)
    assert result.value == date(2026, 6, 7)


def test_bgb_193_weekend_shift():
    # 2026-06-13 is a Saturday.
    result = calculate_deadline(date(2026, 6, 12), 1, "Tage", DeadlineMode.BGB_EVENT, apply_193=True)
    assert result.value == date(2026, 6, 15)
