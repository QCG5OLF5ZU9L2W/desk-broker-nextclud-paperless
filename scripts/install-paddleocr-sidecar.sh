#!/usr/bin/env bash
set -u
BASE="${PAPERLESS_NC_IMPORT_PADDLEOCR_BASE:-$HOME/.local/share/paperless-nc-import/paddleocr-sidecar}"
VENV="$BASE/.venv"
fail(){ echo; echo "ABBRUCH: $*" >&2; exit 1; }
export PATH="$HOME/.local/bin:$PATH"
echo "== Installiere PaddleOCR Sidecar =="
echo "Base: $BASE"
sudo apt update || fail "apt update fehlgeschlagen"
sudo apt install -y poppler-utils pipx || fail "Systempakete fehlgeschlagen"
if ! command -v uv >/dev/null 2>&1; then
  python3 -m pipx ensurepath >/dev/null 2>&1 || true
  export PATH="$HOME/.local/bin:$PATH"
  pipx install uv || fail "uv konnte nicht installiert werden"
fi
mkdir -p "$BASE"
rm -rf "$VENV"
uv python install 3.11 || fail "Python 3.11 konnte nicht installiert werden"
uv venv --seed --python 3.11 "$VENV" || fail "venv konnte nicht erstellt werden"
PY="$VENV/bin/python"
"$PY" -m pip install -U pip setuptools wheel || fail "pip-Grundpakete fehlgeschlagen"
"$PY" -m pip install "numpy<2" Pillow opencv-python-headless || fail "Basisabhängigkeiten fehlgeschlagen"
"$PY" -m pip install paddlepaddle==2.6.2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ --extra-index-url https://pypi.org/simple || fail "paddlepaddle CPU fehlgeschlagen"
"$PY" -m pip install paddleocr==2.7.3 || fail "paddleocr fehlgeschlagen"
FLAGS_use_mkldnn=0 FLAGS_enable_pir_api=0 "$PY" - <<'PY_IMPORT'
import os
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
import paddle
import paddleocr
print("paddle:", paddle.__version__)
print("paddleocr:", getattr(paddleocr, "__version__", "?"))
PY_IMPORT
echo
echo "FERTIG. Sidecar-Python: $PY"
