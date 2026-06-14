from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import Any
import json
import re
import unicodedata


AMOUNT_PATTERN = r"([-+−]?\s*\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|[-+−]?\s*\d+[,.]\d{2})"


@dataclass(slots=True, frozen=True)
class LabelExpression:
    text: str
    weight: float = 0.5
    extractor: str = "label_before_value"

    @property
    def normalized(self) -> str:
        return normalize_label(self.text)


@dataclass(slots=True, frozen=True)
class RoleRuleset:
    schema: int
    locale: str
    role: str
    field_type: str
    value_type: str = ""
    version: str = ""
    labels: list[LabelExpression] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class RoleExtractionCandidate:
    role: str
    field_type: str
    raw_value: str
    label_normalized: str
    extractor: str
    confidence: float


def normalize_label(value: str) -> str:
    """Normalize a fachlicher Label-Anker for matching and community signals.

    This intentionally does not normalize or keep values. Digits are preserved
    here because the privacy filter decides what can leave the machine; built-in
    matching can still tolerate noisy labels. Community upload must call
    community_learning.is_safe_label().
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.casefold()
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = re.sub(r"[\s:_=€$£¥]+", " ", text)
    text = re.sub(r"[^0-9a-zäöüß\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def _label_regex(label_normalized: str) -> str:
    # Match whitespace/OCR spacing flexibly while keeping token order.
    tokens = [re.escape(tok) for tok in label_normalized.split() if tok]
    if not tokens:
        return r"a^"
    return r"\s+".join(tokens)


def _load_ruleset_file(path: resources.abc.Traversable) -> RoleRuleset | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != 1:
        return None
    labels: list[LabelExpression] = []
    for item in data.get("labels") or []:
        if not isinstance(item, dict):
            continue
        text = normalize_label(str(item.get("text", "")))
        if not text:
            continue
        try:
            weight = float(item.get("weight", 0.5))
        except (TypeError, ValueError):
            weight = 0.5
        labels.append(
            LabelExpression(
                text=text,
                weight=max(0.0, min(1.0, weight)),
                extractor=str(item.get("extractor", "label_before_value") or "label_before_value"),
            )
        )
    return RoleRuleset(
        schema=1,
        locale=str(data.get("locale", "de") or "de"),
        role=str(data.get("role", "") or ""),
        field_type=str(data.get("field_type", "") or ""),
        value_type=str(data.get("value_type", "") or ""),
        version=str(data.get("version", "") or ""),
        labels=labels,
    )


def load_builtin_rulesets(*, locale: str = "de", role: str = "") -> list[RoleRuleset]:
    """Load project-shipped rulesets from paperless_nc_import/rulesets/builtin."""
    root = resources.files("paperless_nc_import").joinpath("rulesets", "builtin", locale)
    try:
        files = sorted(p for p in root.iterdir() if p.name.endswith(".json"))
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    out: list[RoleRuleset] = []
    for path in files:
        ruleset = _load_ruleset_file(path)
        if not ruleset or not ruleset.role:
            continue
        if role and ruleset.role != role:
            continue
        out.append(ruleset)
    return out


_FIELD_ROLE_ALIASES_DE: dict[str, set[str]] = {
    "amount.total": {
        "betrag",
        "brutto",
        "endsumme",
        "gesamt",
        "gesamtbetrag",
        "gesamtpreis",
        "kaufpreis",
        "rechnungssumme",
        "rechnungsbetrag",
        "zahlbetrag",
        "zu zahlen",
    },
    "amount.vat": {
        "mehrwertsteuer",
        "mwst",
        "steuerbetrag",
        "umsatzsteuer",
        "ust",
    },
}


def infer_field_role(*, field_name: str, field_type: str, locale: str = "de") -> str:
    """Infer a semantic role from Paperless field name/type as a fallback.

    The stable mapping should ultimately come from config/extraction.field_roles.
    Name inference is only a convenience for first use.
    """
    if locale != "de":
        return ""
    typ = (field_type or "").strip().casefold()
    name = normalize_label(field_name)
    if typ and typ != "monetary":
        return ""
    for role, aliases in _FIELD_ROLE_ALIASES_DE.items():
        for alias in aliases:
            a = normalize_label(alias)
            if name == a or a in name:
                return role
    return ""


def extract_role_candidates(
    *,
    role: str,
    field_type: str,
    text: str,
    locale: str = "de",
    max_label_to_value_chars: int = 90,
) -> list[RoleExtractionCandidate]:
    """Find value candidates for a semantic role using project rulesets.

    Only label anchors are stored in rulesets. The actual values are read from
    the local document text and are never needed for community learning.
    """
    if not role or not text:
        return []
    body = str(text or "").replace("\u00a0", " ").replace("\u202f", " ")
    rulesets = load_builtin_rulesets(locale=locale, role=role)
    candidates: list[RoleExtractionCandidate] = []
    for ruleset in rulesets:
        if ruleset.field_type and field_type and ruleset.field_type.casefold() != field_type.casefold():
            continue
        for label in ruleset.labels:
            label_norm = label.normalized
            if not label_norm:
                continue
            label_rx = _label_regex(label_norm)
            pattern = rf"{label_rx}[^\d\-+−]{{0,{int(max_label_to_value_chars)}}}{AMOUNT_PATTERN}\b"
            try:
                compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            except re.error:
                continue
            for match in compiled.finditer(body):
                raw_value = match.group(1)
                if not raw_value:
                    continue
                distance_penalty = min(0.10, max(0, len(match.group(0)) - len(label_norm)) / 1000)
                candidates.append(
                    RoleExtractionCandidate(
                        role=ruleset.role,
                        field_type=ruleset.field_type or field_type,
                        raw_value=raw_value,
                        label_normalized=label_norm,
                        extractor=label.extractor,
                        confidence=max(0.0, min(1.0, label.weight - distance_penalty)),
                    )
                )
                # Multiple equal labels in the same document usually repeat the
                # same semantic concept. Keep candidates concise for GUI prefill.
                break
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates
