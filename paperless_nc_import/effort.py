from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo

from .deadline import is_public_holiday


@dataclass(frozen=True, slots=True)
class EffortSpec:
    raw: str
    amount: int
    unit: str
    label: str


class EffortParseError(ValueError):
    pass


_PATTERN = re.compile(r"^\s*(\d+)\s*([a-zA-ZäöüÄÖÜ]+)\s*$")


def parse_effort(value: str) -> EffortSpec | None:
    """Parse compact effort strings.

    Supported units:
    - m/min  = minutes
    - h      = hours
    - d/at   = working days (Arbeitstage)
    - cd/kt  = calendar days (Kalendertage)
    - w      = working weeks (5 working days)

    Empty input means: no start date / effort estimate.
    """
    text = (value or "").strip()
    if not text:
        return None
    m = _PATTERN.match(text)
    if not m:
        raise EffortParseError("Aufwand/Vorlauf muss z.B. 5d, 3h, 30m, 2w oder 10kt sein.")
    amount = int(m.group(1))
    unit = m.group(2).casefold()
    if amount < 0:
        raise EffortParseError("Aufwand/Vorlauf darf nicht negativ sein.")
    if unit in {"m", "min", "mins", "minute", "minuten"}:
        return EffortSpec(text, amount, "minutes", f"{amount} Minute(n)")
    if unit in {"h", "std", "stunde", "stunden", "hour", "hours"}:
        return EffortSpec(text, amount, "hours", f"{amount} Stunde(n)")
    if unit in {"d", "at", "arbeitstag", "arbeitstage", "workday", "workdays"}:
        return EffortSpec(text, amount, "workdays", f"{amount} Arbeitstag(e)")
    if unit in {"cd", "kt", "kalendertag", "kalendertage", "tag", "tage", "day", "days"}:
        return EffortSpec(text, amount, "calendar_days", f"{amount} Kalendertag(e)")
    if unit in {"w", "aw", "arbeitswoche", "arbeitswochen", "week", "weeks", "woche", "wochen"}:
        return EffortSpec(text, amount * 5, "workdays", f"{amount} Arbeitswoche(n) = {amount * 5} Arbeitstag(e)")
    raise EffortParseError(f"Unbekannte Aufwandseinheit: {unit!r}. Nutze z.B. 5d, 3h, 30m oder 10kt.")


def is_workday(value: date, holiday_state: str = "") -> bool:
    if value.weekday() >= 5:
        return False
    if holiday_state and is_public_holiday(value, holiday_state):
        return False
    return True


def subtract_workdays(value: datetime, days: int, holiday_state: str = "") -> datetime:
    current = value
    remaining = max(0, int(days))
    while remaining > 0:
        current = current - timedelta(days=1)
        if is_workday(current.date(), holiday_state):
            remaining -= 1
    return current


def compute_start_datetime(due: datetime, effort: EffortSpec | None, holiday_state: str = "") -> datetime | None:
    if not effort or effort.amount <= 0:
        return None
    if effort.unit == "minutes":
        return due - timedelta(minutes=effort.amount)
    if effort.unit == "hours":
        return due - timedelta(hours=effort.amount)
    if effort.unit == "calendar_days":
        return due - timedelta(days=effort.amount)
    if effort.unit == "workdays":
        return subtract_workdays(due, effort.amount, holiday_state)
    return None
