from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

_MONTHS_DE = {
    "januar": 1,
    "jan": 1,
    "februar": 2,
    "feb": 2,
    "märz": 3,
    "maerz": 3,
    "mrz": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
}


def normalize_label(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.casefold()
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = text.replace("€", " eur ")
    text = re.sub(r"[\s:_=]+", " ", text)
    text = re.sub(r"[^0-9a-zäöüß\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def normalize_ocr_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace("\ufeff", "")
    text = text.replace("−", "-")
    return text


def label_to_regex(label_normalized: str) -> str:
    """Build a tolerant regex for OCR-noisy labels.

    It matches normal whitespace between words and optional whitespace between
    characters inside a word. That lets `endsumme` match `E n d s u m m e`
    without adding receipt-specific code.
    """

    tokens: list[str] = []
    for token in normalize_label(label_normalized).split():
        if not token:
            continue
        # Do not make very short tokens too permissive.
        if len(token) <= 2:
            tokens.append(re.escape(token))
        else:
            tokens.append(r"\s*".join(re.escape(ch) for ch in token))
    if not tokens:
        return r"a^"
    return r"\s+".join(tokens)


def normalize_money(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = (
        text.replace("€", "")
        .replace("EUR", "")
        .replace("eur", "")
        .replace("−", "-")
        .replace(" ", "")
        .strip()
    )
    text = re.sub(r"[^0-9,.\-+]", "", text)
    if not text:
        return ""

    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif last_comma >= 0:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        head, tail = text.rsplit(".", 1)
        text = head.replace(".", "") + "." + tail

    try:
        amount = Decimal(text)
    except InvalidOperation:
        return ""
    return f"{amount:.2f}".replace(".", ",")


def normalize_date(value: str) -> str:
    text = normalize_ocr_text(value).strip()
    if not text:
        return ""

    # Prefer dateparser when installed; keep deterministic fallback for tests
    # and offline installations.
    try:  # pragma: no cover - optional dependency branch
        import dateparser  # type: ignore

        parsed = dateparser.parse(
            text,
            languages=["de", "en"],
            settings={"DATE_ORDER": "DMY", "PREFER_DAY_OF_MONTH": "first"},
        )
        if parsed:
            return parsed.date().isoformat()
    except Exception:
        pass

    m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b", text)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return ""

    m = re.search(r"\b(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\s+(\d{2,4})\b", text)
    if m:
        day = int(m.group(1))
        month_name = normalize_label(m.group(2)).replace("ä", "ae")
        month = _MONTHS_DE.get(month_name) or _MONTHS_DE.get(normalize_label(m.group(2)))
        year = int(m.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        if month:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return ""
    return ""


def compact_iban(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def iban_mod97_valid(value: str) -> bool:
    iban = compact_iban(value)
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    digits = ""
    for ch in rearranged:
        if ch.isdigit():
            digits += ch
        elif "A" <= ch <= "Z":
            digits += str(ord(ch) - 55)
        else:
            return False
    remainder = 0
    for ch in digits:
        remainder = (remainder * 10 + int(ch)) % 97
    return remainder == 1
