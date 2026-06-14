#!/usr/bin/env bash
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDF="${1:-$HOME/Documents/nc.5st.eu/Private_Postbox/img2.pdf}"
BASE="${PAPERLESS_NC_IMPORT_PADDLEOCR_BASE:-$HOME/.local/share/paperless-nc-import/paddleocr-sidecar}"
PY="$BASE/.venv/bin/python"
OUT="$BASE/out"
fail(){ echo; echo "ABBRUCH: $*" >&2; exit 1; }
test -f "$PDF" || fail "PDF nicht gefunden: $PDF"
test -x "$PY" || fail "Sidecar-Python fehlt: $PY"
mkdir -p "$OUT"
FLAGS_use_mkldnn=0 FLAGS_enable_pir_api=0 "$PY" "$REPO/paperless_nc_import/extractors/paddleocr_worker.py" --input "$PDF" --output "$OUT" --dpi 300 --max-pages 3 --force
LATEST="$(ls -t "$OUT"/*.paddleocr.txt | head -1)"
echo
echo "== OCR-Text =="
echo "$LATEST"
grep -inE 'zahlen|kredit|karte|summe|gesamt|betrag|eur|mwst|netto|brutto|[0-9]+[,.][0-9]{2}' "$LATEST" | head -160 || true
