from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

from .extraction_rulesets import infer_field_role
from .extractors import extract_role_values


@dataclass(slots=True)
class CustomFieldExtractionRule:
    """Configurable OCR/text extraction rule for Paperless custom fields.

    field_id is the stable primary key. field_name is intentionally kept as a
    readable hint and optional fallback so configs remain understandable and can
    still be shared between installations where IDs differ.
    """

    field_id: int | None = None
    field_name: str = ""
    field_type: str = ""
    source: str = "ocr_text"
    extractor: str = "regex"
    patterns: list[str] = field(default_factory=list)
    group: int | str = 1
    normalize: str = ""
    flags: list[str] = field(default_factory=lambda: ["ignorecase", "multiline"])
    priority: int = 100
    enabled: bool = True
    label: str = ""


@dataclass(slots=True)
class ExtractionMatch:
    value: str
    raw: str
    rule: CustomFieldExtractionRule
    confidence: float = 1.0
    role: str = ""
    label_normalized: str = ""
    extractor: str = ""


_AMOUNT_PATTERN = r"([-+−]?\s*\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|[-+−]?\s*\d+[,.]\d{2})"
_RECEIPT_TOTAL_LABEL = (
    r"(?:"
    r"e\s*n\s*d\s*s?\s*u\s*m\s*m?\s*e|"
    r"end\s*summe|"
    r"endsumm?e|"
    r"endbetrag|"
    r"gesamt(?:betrag)?|"
    r"zu\s*zahlen|"
    r"betrag\s+gezahlt|"
    r"summe"
    r")"
)
_RECEIPT_TOTAL_PATTERNS = [
    rf"^\s*{_RECEIPT_TOTAL_LABEL}\s*(?:€|eur)?\s*[:=]?\s*{_AMOUNT_PATTERN}\b",
    rf"{_RECEIPT_TOTAL_LABEL}[^\d\-+−]{{0,28}}{_AMOUNT_PATTERN}\b",
]

_FLAG_MAP = {
    "i": re.IGNORECASE,
    "ignorecase": re.IGNORECASE,
    "ignore_case": re.IGNORECASE,
    "m": re.MULTILINE,
    "multiline": re.MULTILINE,
    "multi_line": re.MULTILINE,
    "s": re.DOTALL,
    "dotall": re.DOTALL,
    "dot_all": re.DOTALL,
}


def _regex_flags(names: list[str] | None) -> re.RegexFlag:
    flags = re.RegexFlag(0)
    for name in names or []:
        key = str(name).strip().casefold()
        if key in _FLAG_MAP:
            flags |= _FLAG_MAP[key]
            continue
        # Accept compact forms such as "im" in addition to ["i", "m"].
        for char in key:
            flags |= _FLAG_MAP.get(char, re.RegexFlag(0))
    return flags


def _safe_group(match: re.Match[str], group: int | str) -> str:
    try:
        return str(match.group(group) or "")
    except (IndexError, KeyError):
        return ""


def _normalize_text(text: str) -> str:
    return (
        (text or "")
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\ufeff", "")
    )


def _source_text(rule: CustomFieldExtractionRule, fallback_text: str, sources: dict[str, str] | None) -> str:
    if not sources:
        return fallback_text
    key = (rule.source or "ocr_text").strip().casefold()
    aliases = {
        "ocr": "ocr_text",
        "text": "document_text",
        "pdf_text": "document_text",
        "document": "document_text",
        "file": "filename",
        "file_name": "filename",
        "local_path": "path",
    }
    key = aliases.get(key, key)
    return sources.get(key) or fallback_text


def normalize_monetary(value: str) -> str:
    """Normalize German/English-looking money strings to GUI-friendly decimal-comma text.

    The GUI remains editable for German users, while validators.parse_number()
    accepts both decimal comma and decimal dot when the field is submitted.
    """
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
    text = re.sub(r"[^0-9,\.\-+]", "", text)
    if not text:
        return ""

    # If both separators are present, the last one is very likely the decimal
    # separator; the other one is treated as a thousands separator.
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif last_comma >= 0:
        text = text.replace(".", "").replace(",", ".")
    else:
        # Keep a single decimal dot. Multiple dots are assumed to include
        # thousands separators except for the last decimal dot.
        if text.count(".") > 1:
            head, tail = text.rsplit(".", 1)
            text = head.replace(".", "") + "." + tail
    return text.replace(".", ",")


def normalize_value(value: str, mode: str, field_type: str = "") -> str:
    mode_key = (mode or "").strip().casefold()
    typ = (field_type or "").strip().casefold()
    if mode_key in {"monetary", "money", "euro", "eur", "decimal"} or typ == "monetary":
        return normalize_monetary(value)
    if mode_key in {"strip", "text", "string"}:
        return str(value or "").strip()
    return str(value or "").strip()


def _field_matches(
    rule: CustomFieldExtractionRule,
    *,
    field_id: int,
    field_name: str,
    field_type: str,
) -> bool:
    if not rule.enabled:
        return False
    if rule.field_id is not None:
        if int(rule.field_id) != int(field_id):
            return False
    elif rule.field_name:
        if rule.field_name.strip().casefold() != (field_name or "").strip().casefold():
            return False
    else:
        return False

    if rule.field_type and field_type:
        if rule.field_type.strip().casefold() != field_type.strip().casefold():
            return False
    return True


def _patterns_for_rule(rule: CustomFieldExtractionRule) -> list[str]:
    extractor = (rule.extractor or "regex").strip().casefold()
    if rule.patterns:
        return list(rule.patterns)
    if extractor in {"receipt_total", "receipt-total", "kassenbon_total", "invoice_total"}:
        return list(_RECEIPT_TOTAL_PATTERNS)
    return []


def extract_custom_field_matches(
    *,
    field_id: int,
    field_name: str,
    field_type: str,
    text: str,
    rules: list[CustomFieldExtractionRule],
    sources: dict[str, str] | None = None,
    field_role: str = "",
    locale: str = "de",
    use_builtin_rulesets: bool | None = None,
) -> list[ExtractionMatch]:
    if use_builtin_rulesets is None:
        use_builtin_rulesets = bool(field_role) or not rules
    matches: list[ExtractionMatch] = []
    for rule in sorted(rules, key=lambda r: int(r.priority)):
        if not _field_matches(rule, field_id=field_id, field_name=field_name, field_type=field_type):
            continue
        body = _normalize_text(_source_text(rule, text, sources))
        if not body:
            continue
        flags = _regex_flags(rule.flags)
        for pattern in _patterns_for_rule(rule):
            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue
            found = compiled.search(body)
            if not found:
                continue
            raw = _safe_group(found, rule.group) or (found.group(0) if found else "")
            value = normalize_value(raw, rule.normalize, field_type)
            if value:
                matches.append(
                    ExtractionMatch(
                        value=value,
                        raw=raw,
                        rule=rule,
                        confidence=1.0,
                        role="",
                        label_normalized=rule.label or "",
                        extractor=rule.extractor or "regex",
                    )
                )
                # One hit per rule is enough for GUI prefilling; later versions can
                # expose all candidates if we add a proper review UI.
                break
    # If no explicit user/developer rule matched, fall back to project-shipped
    # role rulesets. These rulesets contain only label anchors (e.g.
    # "fahrzeugpreis inklusive nebenkosten"), never values or OCR excerpts.
    if not matches and use_builtin_rulesets:
        role = (field_role or "").strip() or infer_field_role(
            field_name=field_name, field_type=field_type, locale=locale
        )
        for candidate in extract_role_values(
            role=role,
            field_type=field_type,
            text=text,
            locale=locale,
            sources=sources,
        ):
            value = candidate.value or normalize_value(candidate.raw_value, "monetary", field_type)
            if not value:
                continue
            matches.append(
                ExtractionMatch(
                    value=value,
                    raw=candidate.raw_value,
                    rule=CustomFieldExtractionRule(
                        field_id=field_id,
                        field_name=field_name,
                        field_type=field_type,
                        source="ocr_text",
                        extractor=candidate.extractor or candidate.backend or "extractor_adapter",
                        normalize="",
                        priority=1000,
                        label=candidate.label_normalized,
                    ),
                    confidence=candidate.confidence,
                    role=candidate.role,
                    label_normalized=candidate.label_normalized,
                    extractor=candidate.extractor or candidate.backend,
                )
            )
    return matches


def extract_custom_field_value(
    *,
    field_id: int,
    field_name: str,
    field_type: str,
    text: str,
    rules: list[CustomFieldExtractionRule],
    sources: dict[str, str] | None = None,
    field_role: str = "",
    locale: str = "de",
    use_builtin_rulesets: bool | None = None,
) -> ExtractionMatch | None:
    matches = extract_custom_field_matches(
        field_id=field_id,
        field_name=field_name,
        field_type=field_type,
        text=text,
        rules=rules,
        sources=sources,
        field_role=field_role,
        locale=locale,
        use_builtin_rulesets=use_builtin_rulesets,
    )
    return matches[0] if matches else None
