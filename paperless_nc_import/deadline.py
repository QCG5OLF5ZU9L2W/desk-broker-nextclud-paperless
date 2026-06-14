from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
import calendar
from functools import lru_cache


class DeadlineMode(str, Enum):
    """Supported date-calculation modes.

    reminder: plain calendar reminder.  A month is a calendar month, not 30 days.
    bgb_event: event deadline under § 187 Abs. 1 BGB; the event day is not counted.
    bgb_start: beginning-of-day deadline under § 187 Abs. 2 BGB; the start day is counted.
    """

    REMINDER = "reminder"
    BGB_EVENT = "bgb_event"
    BGB_START = "bgb_start"


@dataclass(frozen=True)
class DeadlineResult:
    value: date
    note: str


GERMAN_STATE_LABELS: list[tuple[str, str]] = [
    ("", "keine Feiertage"),
    ("DE", "bundesweite Feiertage"),
    ("BW", "Baden-Württemberg"),
    ("BY", "Bayern"),
    ("BE", "Berlin"),
    ("BB", "Brandenburg"),
    ("HB", "Bremen"),
    ("HH", "Hamburg"),
    ("HE", "Hessen"),
    ("MV", "Mecklenburg-Vorpommern"),
    ("NI", "Niedersachsen"),
    ("NW", "Nordrhein-Westfalen"),
    ("RP", "Rheinland-Pfalz"),
    ("SL", "Saarland"),
    ("SN", "Sachsen"),
    ("ST", "Sachsen-Anhalt"),
    ("SH", "Schleswig-Holstein"),
    ("TH", "Thüringen"),
]


def is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_calendar_months(value: date, months: int) -> date:
    """Add calendar months, clamping to the last day if the target day is absent.

    This matches the § 188 Abs. 3 BGB fallback for months without the corresponding day and is also
    the expected behaviour for simple reminder dates.
    """

    month0 = value.month - 1 + months
    year = value.year + month0 // 12
    month = month0 % 12 + 1
    day = min(value.day, last_day_of_month(year, month))
    return date(year, month, day)


def add_calendar_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        # 29 February -> 28 February in non-leap target years.
        return value.replace(year=value.year + years, day=28)


@lru_cache(maxsize=128)
def _holiday_set(year: int, state: str) -> set[date]:
    code = (state or "").upper()
    if not code:
        return set()
    try:
        import holidays  # type: ignore
    except Exception:
        return set()

    subdiv = None if code == "DE" else code
    try:
        return set(holidays.country_holidays("DE", subdiv=subdiv, years=[year]).keys())
    except Exception:
        return set()


def is_public_holiday(value: date, state: str) -> bool:
    return value in _holiday_set(value.year, state)


def apply_bgb_193(value: date, state: str = "") -> tuple[date, bool, list[str]]:
    """Move deadline to next working day under § 193 BGB.

    Saturday/Sunday are handled always.  Public holidays are handled when the optional `holidays`
    package is available and a German state/federal code is selected.
    """

    shifted = False
    reasons: list[str] = []
    current = value
    while True:
        reason = ""
        if current.weekday() == 5:
            reason = "Sonnabend"
        elif current.weekday() == 6:
            reason = "Sonntag"
        elif state and is_public_holiday(current, state):
            reason = "Feiertag"
        if not reason:
            break
        shifted = True
        reasons.append(f"{current.isoformat()} ({reason})")
        current = current + timedelta(days=1)
    return current, shifted, reasons


def calculate_deadline(
    base: date,
    amount: int,
    unit: str,
    mode: DeadlineMode | str = DeadlineMode.REMINDER,
    apply_193: bool = False,
    holiday_state: str = "",
) -> DeadlineResult:
    if amount < 0:
        raise ValueError("amount must be non-negative")
    mode = DeadlineMode(mode)
    unit_key = unit.casefold().strip()
    if unit_key in {"tag", "tage", "days", "day"}:
        if mode == DeadlineMode.BGB_START and amount > 0:
            result = base + timedelta(days=amount - 1)
            note = f"§187 Abs.2/§188 Abs.1 BGB: {amount} Tag(e), Anfangstag zählt mit"
        else:
            result = base + timedelta(days=amount)
            note = f"{amount} Tag(e) ab {base.isoformat()}"
            if mode == DeadlineMode.BGB_EVENT:
                note = f"§187 Abs.1/§188 Abs.1 BGB: {amount} Tag(e), Ereignistag zählt nicht mit"
    elif unit_key in {"woche", "wochen", "weeks", "week"}:
        if mode == DeadlineMode.BGB_START and amount > 0:
            result = base + timedelta(weeks=amount) - timedelta(days=1)
            note = f"§187 Abs.2/§188 Abs.2 BGB: {amount} Woche(n), Ende am Vortag"
        else:
            result = base + timedelta(weeks=amount)
            note = f"{amount} Woche(n) ab {base.isoformat()}"
            if mode == DeadlineMode.BGB_EVENT:
                note = f"§187 Abs.1/§188 Abs.2 BGB: {amount} Woche(n), Ereignistag zählt nicht mit"
    elif unit_key in {"monat", "monate", "months", "month"}:
        if mode == DeadlineMode.BGB_START and amount > 0:
            result = add_calendar_months(base, amount) - timedelta(days=1)
            note = f"§187 Abs.2/§188 Abs.2 BGB: {amount} Monat(e), Ende am Vortag"
        else:
            result = add_calendar_months(base, amount)
            note = f"{amount} Kalendermonat(e) ab {base.isoformat()}"
            if mode == DeadlineMode.BGB_EVENT:
                note = f"§187 Abs.1/§188 Abs.2/Abs.3 BGB: {amount} Monat(e), Ereignistag zählt nicht mit"
    elif unit_key in {"jahr", "jahre", "years", "year"}:
        if mode == DeadlineMode.BGB_START and amount > 0:
            result = add_calendar_years(base, amount) - timedelta(days=1)
            note = f"§187 Abs.2/§188 Abs.2 BGB: {amount} Jahr(e), Ende am Vortag"
        else:
            result = add_calendar_years(base, amount)
            note = f"{amount} Kalenderjahr(e) ab {base.isoformat()}"
            if mode == DeadlineMode.BGB_EVENT:
                note = f"§187 Abs.1/§188 Abs.2/Abs.3 BGB: {amount} Jahr(e), Ereignistag zählt nicht mit"
    else:
        raise ValueError(f"Unsupported unit: {unit}")

    if apply_193 and mode != DeadlineMode.REMINDER:
        shifted_value, shifted, reasons = apply_bgb_193(result, holiday_state)
        if shifted:
            result = shifted_value
            note += "; §193 BGB verschoben wegen " + ", ".join(reasons)
        else:
            note += "; §193 BGB: keine Verschiebung"
    return DeadlineResult(result, note)
