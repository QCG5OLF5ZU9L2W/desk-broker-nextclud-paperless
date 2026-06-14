#!/usr/bin/env bash
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${PAPERLESS_NC_IMPORT_PADDLEOCR_BASE:-$HOME/.local/share/paperless-nc-import/paddleocr-sidecar}"
PY="${PAPERLESS_NC_IMPORT_PADDLEOCR_PYTHON:-$BASE/.venv/bin/python}"
OUT="${PAPERLESS_NC_IMPORT_PADDLEOCR_CACHE_DIR:-$BASE/out}"

fail() {
  echo
  echo "ABBRUCH: $*" >&2
  exit 1
}

test -x "$PY" || fail "PaddleOCR-Sidecar-Python fehlt: $PY"
test "$#" -ge 1 || fail "Nutzung: scripts/precache-paddleocr.sh DATEI.pdf [weitere.pdf]"

for file in "$@"; do
  test -f "$file" || {
    echo "WARN: Datei fehlt: $file"
    continue
  }

  echo
  echo "== PaddleOCR precache: $file =="
  FLAGS_use_mkldnn=0 FLAGS_enable_pir_api=0 "$PY" \
    "$REPO/paperless_nc_import/extractors/paddleocr_worker.py" \
    --input "$file" \
    --output "$OUT" \
    --dpi "${PAPERLESS_NC_IMPORT_PADDLEOCR_DPI:-300}" \
    --max-pages "${PAPERLESS_NC_IMPORT_PADDLEOCR_MAX_PAGES:-3}" \
    --min-score "${PAPERLESS_NC_IMPORT_PADDLEOCR_MIN_SCORE:-0.50}" \
    --force || exit 1
done
