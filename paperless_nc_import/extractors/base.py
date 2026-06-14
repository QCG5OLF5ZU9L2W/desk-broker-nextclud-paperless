from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class ExtractorInput:
    """Local-only extraction input.

    The text and paths in this object must never be used for community learning
    payloads. Community learning may only use the normalized label/result
    information from ExtractorResult after privacy filtering.
    """

    role: str
    field_type: str
    text: str = ""
    locale: str = "de"
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> Path | None:
        raw = self.sources.get("path") or self.sources.get("filename") or ""
        if not raw:
            return None
        return Path(raw)


@dataclass(slots=True, frozen=True)
class ExtractorResult:
    role: str
    field_type: str
    value: str
    raw_value: str
    label_normalized: str = ""
    extractor: str = ""
    backend: str = ""
    confidence: float = 0.0
    explanation: str = ""


class BaseExtractor:
    """Small adapter interface for all extraction backends."""

    name = "base"
    priority = 100

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        raise NotImplementedError
