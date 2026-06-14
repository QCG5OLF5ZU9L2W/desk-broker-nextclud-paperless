from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
from pathlib import Path
from typing import Any

import yaml

from .normalizers import normalize_label


@dataclass(slots=True, frozen=True)
class RuleLabel:
    text: str
    weight: float = 0.5
    kind: str = "label"
    extractor: str = "label_before_value"

    @property
    def normalized(self) -> str:
        return normalize_label(self.text)


@dataclass(slots=True, frozen=True)
class RoleRuleset:
    schema: int
    locale: str
    role: str
    field_type: str = ""
    value_type: str = ""
    version: str = ""
    labels: list[RuleLabel] = field(default_factory=list)


def _labels_from_any(raw: Any, *, default_kind: str = "label") -> list[RuleLabel]:
    labels: list[RuleLabel] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                labels.append(RuleLabel(text=normalize_label(item), kind=default_kind))
            elif isinstance(item, dict):
                text = normalize_label(str(item.get("text", "") or ""))
                if not text:
                    continue
                try:
                    weight = float(item.get("weight", 0.5))
                except (TypeError, ValueError):
                    weight = 0.5
                labels.append(
                    RuleLabel(
                        text=text,
                        weight=max(0.0, min(1.0, weight)),
                        kind=str(item.get("kind", default_kind) or default_kind),
                        extractor=str(item.get("extractor", "label_before_value") or "label_before_value"),
                    )
                )
    elif isinstance(raw, dict):
        for kind, values in raw.items():
            labels.extend(_labels_from_any(values, default_kind=str(kind)))
    return labels


def _load_structured_file(path: resources.abc.Traversable | Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        if str(path).endswith((".yaml", ".yml")):
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _ruleset_from_data(data: dict[str, Any]) -> RoleRuleset | None:
    if int(data.get("schema", 1) or 1) != 1:
        return None
    role = str(data.get("role", "") or "").strip()
    if not role:
        return None
    labels: list[RuleLabel] = []
    # Backwards compatible flat JSON format.
    labels.extend(_labels_from_any(data.get("labels") or [], default_kind="label"))
    # New grouped format: label_groups.strong_total / date_label / etc.
    labels.extend(_labels_from_any(data.get("label_groups") or {}, default_kind="label"))
    # New alias: contexts.
    labels.extend(_labels_from_any(data.get("contexts") or {}, default_kind="label"))

    seen: set[tuple[str, str]] = set()
    deduped: list[RuleLabel] = []
    for label in labels:
        key = (label.kind, label.normalized)
        if not label.normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(label)

    return RoleRuleset(
        schema=1,
        locale=str(data.get("locale", "de") or "de"),
        role=role,
        field_type=str(data.get("field_type", "") or ""),
        value_type=str(data.get("value_type", "") or ""),
        version=str(data.get("version", "") or ""),
        labels=deduped,
    )


def load_builtin_rulesets(*, locale: str = "de", role: str = "") -> list[RoleRuleset]:
    root = resources.files("paperless_nc_import").joinpath("rulesets", "builtin", locale)
    try:
        files = sorted(
            p for p in root.iterdir() if p.name.endswith((".json", ".yaml", ".yml"))
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    out: list[RoleRuleset] = []
    for path in files:
        data = _load_structured_file(path)
        if not data:
            continue
        ruleset = _ruleset_from_data(data)
        if not ruleset:
            continue
        if role and ruleset.role != role:
            continue
        out.append(ruleset)
    return out
