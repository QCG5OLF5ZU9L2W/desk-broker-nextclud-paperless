#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

BAD_LABEL_PATTERNS = [
    ("digit", re.compile(r"\d")),
    ("email", re.compile(r"@")),
    ("url", re.compile(r"https?://|www\.", re.IGNORECASE)),
    ("path", re.compile(r"[\\/]")),
    ("iban", re.compile(r"\b[a-z]{2}\s*\d{2}(?:\s*[0-9a-z]){10,}\b", re.IGNORECASE)),
    ("vat_id", re.compile(r"\bde\s*\d{9}\b", re.IGNORECASE)),
    ("specific_id", re.compile(r"\b[a-z]{1,5}[-_/]?\d{3,}\b", re.IGNORECASE)),
]

ALLOWED_ROLES = {
    "amount.total",
    "amount.vat",
    "amount.net",
    "date.invoice",
    "date.due",
    "date.service",
    "bank.iban",
}


def die(path: Path, msg: str) -> None:
    print(f"ERROR: {path}: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load(path: Path) -> dict[str, Any]:
    try:
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(path, f"cannot parse: {exc}")
    if not isinstance(data, dict):
        die(path, "top-level value must be an object")
    return data


def iter_labels(value: Any):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                yield str(item.get("text", "") or "")
    elif isinstance(value, dict):
        for nested in value.values():
            yield from iter_labels(nested)


def validate(path: Path) -> None:
    data = load(path)
    if int(data.get("schema", 0) or 0) != 1:
        die(path, "schema must be 1")
    role = str(data.get("role", "") or "")
    if role not in ALLOWED_ROLES:
        die(path, f"role not allowed: {role!r}")
    locale = str(data.get("locale", "") or "")
    if locale != "de":
        die(path, "only locale de is expected in this path")
    labels = list(iter_labels(data.get("labels") or []))
    labels.extend(iter_labels(data.get("label_groups") or {}))
    labels.extend(iter_labels(data.get("contexts") or {}))
    if not labels:
        die(path, "no labels found")
    for raw in labels:
        label = raw.strip().casefold()
        if len(label) < 2:
            die(path, f"label too short: {raw!r}")
        if len(label) > 80:
            die(path, f"label too long: {raw!r}")
        for name, pattern in BAD_LABEL_PATTERNS:
            if pattern.search(label):
                die(path, f"privacy filter {name} failed for label: {raw!r}")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("paperless_nc_import/rulesets")
    files = sorted(p for p in root.rglob("*") if p.suffix in {".json", ".yaml", ".yml"})
    if not files:
        die(root, "no ruleset files found")
    for path in files:
        validate(path)
    print(f"OK: validated {len(files)} ruleset file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
