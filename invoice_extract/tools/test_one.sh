#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDF="${1:?Usage: $0 <pdf>}"
READER="${INVOICE_READER:-tesseract}"
invoice2data \
  --template-folder "$ROOT/templates/de" \
  --exclude-built-in-templates \
  --input-reader "$READER" \
  --output-format json \
  --debug \
  "$PDF"
