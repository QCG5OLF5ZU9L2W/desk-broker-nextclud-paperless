#!/usr/bin/env bash
set -euo pipefail

REPO_URL_DEFAULT="git@github.com:QCG5OLF5ZU9L2W/desk-broker-nextclud-paperless.git"
INSTALL_BASE_DEFAULT="$HOME/Documents"
PROJECT_DIR_NAME_DEFAULT="desk-broker-nextclud-paperless"

REPO_URL="${REPO_URL:-$REPO_URL_DEFAULT}"
INSTALL_BASE="${INSTALL_BASE:-$INSTALL_BASE_DEFAULT}"
PROJECT_DIR_NAME="${PROJECT_DIR_NAME:-$PROJECT_DIR_NAME_DEFAULT}"
PROJECT_DIR="$INSTALL_BASE/$PROJECT_DIR_NAME"
INSTALL_NAUTILUS="${INSTALL_NAUTILUS:-1}"
EXTRAS="${EXTRAS:-}"

say() { printf '\n== %s ==\n' "$*"; }
fail() { printf '\nABBRUCH: %s\n' "$*" >&2; exit 1; }

say "Desk Broker Installer"
printf 'Repo:        %s\n' "$REPO_URL"
printf 'Install dir: %s\n' "$PROJECT_DIR"
printf 'Extras:      %s\n' "${EXTRAS:-none}"

if command -v apt >/dev/null 2>&1; then
  say "Systempakete installieren"
  sudo apt update
  sudo apt install -y \
    git make rsync \
    python3 python3-venv python3-pip python3-dev build-essential \
    libgl1 libegl1 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
    libxcb-xfixes0 libxcb-xinput0 \
    ocrmypdf tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
    poppler-utils ghostscript qpdf unpaper pngquant
else
  say "apt nicht gefunden"
  echo "Systempakete bitte manuell installieren."
fi

mkdir -p "$INSTALL_BASE"

if [ -d "$PROJECT_DIR/.git" ]; then
  say "Repository aktualisieren"
  cd "$PROJECT_DIR"
  git pull --ff-only
elif [ -d "$PROJECT_DIR" ]; then
  fail "$PROJECT_DIR existiert, ist aber kein Git-Repository. Bitte vorher umbenennen oder löschen."
else
  say "Repository klonen"
  cd "$INSTALL_BASE"
  git clone "$REPO_URL" "$PROJECT_DIR_NAME"
  cd "$PROJECT_DIR"
fi

test -f pyproject.toml || fail "pyproject.toml fehlt. Repository-Struktur ist nicht korrekt."
test -d paperless_nc_import || fail "paperless_nc_import fehlt. Repository-Struktur ist nicht korrekt."

say "Virtuelle Python-Umgebung"
python3 -m venv .venv
PY=".venv/bin/python"
test -x "$PY" || fail "venv-Python fehlt."

say "Python-Paket installieren"
"$PY" -m pip install -U pip
if [ -n "$EXTRAS" ]; then
  "$PY" -m pip install -e ".[${EXTRAS}]"
else
  "$PY" -m pip install -e .
fi
"$PY" -m pip install pytest

say "Checks"
"$PY" -m compileall paperless_nc_import
PYTHONPATH=. "$PY" -m pytest -q
if [ -f scripts/validate_rulesets.py ]; then
  "$PY" scripts/validate_rulesets.py paperless_nc_import/rulesets/builtin
fi

say "Nutzerkonfiguration"
mkdir -p "$HOME/.config/paperless-nc-import"
if [ ! -f "$HOME/.config/paperless-nc-import/config.yaml" ]; then
  cp configs/config.example.yaml "$HOME/.config/paperless-nc-import/config.yaml"
  echo "Config angelegt: $HOME/.config/paperless-nc-import/config.yaml"
else
  echo "Config existiert bereits: $HOME/.config/paperless-nc-import/config.yaml"
fi

if [ "$INSTALL_NAUTILUS" = "1" ] && [ -f Makefile ]; then
  say "Nautilus-Integration"
  make install-nautilus || echo "WARNUNG: Nautilus-Integration konnte nicht installiert werden."
  nautilus -q 2>/dev/null || true
fi

say "Fertig"
echo "Start GUI:"
echo "  cd '$PROJECT_DIR'"
echo "  . .venv/bin/activate"
echo "  paperless-nc-import --gui"
echo
echo "Doctor:"
echo "  paperless-nc-import --doctor --startup-log --no-cache"
