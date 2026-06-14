#!/usr/bin/env bash
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDF="${1:-}"

fail() {
  echo "ABBRUCH: $*" >&2
  exit 1
}

test -n "$PDF" || fail "Nutzung: scripts/debug-date-extraction.sh /pfad/datei.pdf"
test -f "$PDF" || fail "PDF nicht gefunden: $PDF"

cd "$REPO" || fail "Repo nicht gefunden"
PY=".venv/bin/python"
test -x "$PY" || PY="python3"

if [ -x scripts/precache-paddleocr.sh ]; then
  scripts/precache-paddleocr.sh "$PDF" >/dev/null || true
fi

PYTHONPATH=. PAPERLESS_NC_IMPORT_PADDLEOCR_ENABLED=1 "$PY" - "$PDF" <<'PY'
import sys
from paperless_nc_import.extraction import extract_custom_field_value

pdf = sys.argv[1]
for role in ("date.invoice", "date.due", "amount.total"):
    field_type = "date" if role.startswith("date.") else "monetary"
    m = extract_custom_field_value(
        field_id=0,
        field_name=role,
        field_type=field_type,
        text="",
        rules=[],
        field_role=role,
        sources={"path": pdf, "paddleocr": {"enabled": True, "run_policy": "on_demand"}},
        locale="de",
    )
    print(role, "=>", m)
PY
