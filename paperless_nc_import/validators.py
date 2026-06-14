from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

IBAN_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$")


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def is_valid_iban(value: str) -> bool:
    iban = normalize_iban(value)
    if not IBAN_RE.match(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif "A" <= ch <= "Z":
            numeric += str(ord(ch) - 55)
        else:
            return False
    # Streaming mod 97 avoids giant integers on small Python builds.
    mod = 0
    for ch in numeric:
        mod = (mod * 10 + int(ch)) % 97
    return mod == 1


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "ja", "on", "wahr", "x"}


def _normalize_number_text(value: str, *, integer: bool = False) -> str:
    text = (
        str(value or "")
        .strip()
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("−", "-")
    )
    text = re.sub(r"[^0-9,\.\-+]", "", text)
    if not text:
        return ""
    if integer:
        return text.replace(".", "").replace(",", "")

    comma = text.rfind(",")
    dot = text.rfind(".")
    if comma >= 0 and dot >= 0:
        # The rightmost separator is almost always the decimal separator.
        if comma > dot:
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")

    if comma >= 0:
        # Existing German behaviour: comma is decimal separator.
        return text.replace(".", "").replace(",", ".")

    if dot >= 0:
        parts = text.split(".")
        if len(parts) == 2:
            head, tail = parts
            # Preserve old German-thousands behaviour for values such as 1.234,
            # but allow OCR/POS totals such as 14.64 to be parsed correctly.
            if len(tail) == 3 and len(head.lstrip("+-")) <= 3:
                return head + tail
            return text
        head, tail = text.rsplit(".", 1)
        if len(tail) == 2:
            return head.replace(".", "") + "." + tail
        return text.replace(".", "")

    return text


def parse_number(value: str, *, integer: bool = False) -> int | float | None:
    text = _normalize_number_text(value, integer=integer)
    if not text:
        return None
    try:
        if integer:
            return int(Decimal(text))
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return None
