from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import re

from .extraction_rulesets import normalize_label


@dataclass(slots=True, frozen=True)
class CommunityLearningSignal:
    """A GDPR-minimized learning signal.

    This object must never contain document values. It only says that a
    normalized label anchor was useful for a semantic field role.
    """

    schema: int
    locale: str
    field_role: str
    field_type: str
    extractor: str
    label_normalized: str
    result: str
    app_version: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


_BAD_LABEL_PATTERNS = [
    ("digit", re.compile(r"\d")),
    ("email", re.compile(r"@")),
    ("url", re.compile(r"https?://|www\.")),
    ("path", re.compile(r"[\\/]")),
    ("iban", re.compile(r"\b[a-z]{2}\s*\d{2}(?:\s*[0-9a-z]){10,}\b", re.IGNORECASE)),
    ("vat_id", re.compile(r"\bde\s*\d{9}\b", re.IGNORECASE)),
    ("too_specific_id", re.compile(r"\b[a-z]{1,5}[-_/]?\d{3,}\b", re.IGNORECASE)),
]

_ALLOWED_RESULTS = {"accepted", "rejected", "corrected"}


def unsafe_label_reason(label: str) -> str:
    normalized = normalize_label(label)
    if not normalized:
        return "empty"
    if len(normalized) < 2:
        return "too_short"
    if len(normalized) > 80:
        return "too_long"
    for name, pattern in _BAD_LABEL_PATTERNS:
        if pattern.search(normalized):
            return name
    return ""


def is_safe_label(label: str) -> bool:
    return unsafe_label_reason(label) == ""


def build_community_signal(
    *,
    label: str,
    field_role: str,
    field_type: str,
    extractor: str,
    result: str,
    locale: str = "de",
    app_version: str = "",
) -> CommunityLearningSignal | None:
    """Build a safe signal or return None if the label must not leave the client."""
    normalized = normalize_label(label)
    if unsafe_label_reason(normalized):
        return None
    result_key = (result or "").strip().casefold()
    if result_key not in _ALLOWED_RESULTS:
        return None
    if not field_role or not extractor:
        return None
    return CommunityLearningSignal(
        schema=1,
        locale=locale,
        field_role=field_role,
        field_type=field_type,
        extractor=extractor,
        label_normalized=normalized,
        result=result_key,
        app_version=app_version,
    )
