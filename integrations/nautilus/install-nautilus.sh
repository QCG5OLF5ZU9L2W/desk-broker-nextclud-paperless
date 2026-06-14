#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV:-$PROJECT_DIR/.venv}"
APP_BIN="$VENV_DIR/bin/paperless-nc-import"
LOCAL_BIN_DIR="${HOME}/.local/bin"
NAUTILUS_DIR="${HOME}/.local/share/nautilus/scripts"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/paperless-nc-import"
WRAPPER="$LOCAL_BIN_DIR/paperless-nc-import"
SCRIPT_NORMAL="$NAUTILUS_DIR/An Paperless senden"
SCRIPT_DRYRUN="$NAUTILUS_DIR/An Paperless senden (Dry-run)"

mkdir -p "$LOCAL_BIN_DIR" "$NAUTILUS_DIR" "$STATE_DIR"

if [[ ! -x "$APP_BIN" ]]; then
  cat >&2 <<MSG
ABBRUCH: paperless-nc-import ist in der Projekt-venv nicht ausführbar:
  $APP_BIN

Bitte im Projektordner zuerst ausführen:
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -U pip
  pip install -e .
MSG
  exit 1
fi

cat > "$WRAPPER" <<EOF_WRAPPER
#!/usr/bin/env bash
set -Eeuo pipefail
APP_BIN="$APP_BIN"
if [[ ! -x "\$APP_BIN" ]]; then
  msg="paperless-nc-import nicht gefunden oder nicht ausführbar: \$APP_BIN"
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title="Paperless Import" --text="\$msg"
  else
    printf '%s\n' "\$msg" >&2
  fi
  exit 127
fi
exec "\$APP_BIN" "\$@"
EOF_WRAPPER
chmod 0755 "$WRAPPER"

write_nautilus_script() {
  local target="$1"
  local dry_run="$2"
  cat > "$target" <<'EOF_SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

APP="${HOME}/.local/bin/paperless-nc-import"
LOGDIR="${XDG_STATE_HOME:-$HOME/.local/state}/paperless-nc-import"
LOGFILE="$LOGDIR/nautilus.log"
mkdir -p "$LOGDIR"

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '%s %s\n' "$(ts)" "$*" >> "$LOGFILE"; }
notify_error() {
  local msg="$1"
  log "ERROR: $msg"
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title="Paperless Import" --text="$msg" >/dev/null 2>&1 || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "Paperless Import" "$msg" >/dev/null 2>&1 || true
  fi
}

decode_file_uri() {
  python3 - "$1" <<'PY'
from urllib.parse import urlparse, unquote
import sys
uri = sys.argv[1]
p = urlparse(uri)
if p.scheme == "file":
    print(unquote(p.path))
PY
}

append_path() {
  local item="$1"
  [[ -n "$item" ]] || return 0
  if [[ "$item" == file://* ]]; then
    local decoded
    decoded="$(decode_file_uri "$item" || true)"
    [[ -n "$decoded" ]] && SELECTED+=("$decoded")
  elif [[ "$item" == *://* ]]; then
    log "IGNORIERE nicht-lokale URI: $item"
  else
    SELECTED+=("$item")
  fi
}

SELECTED=()

# Moderne Nautilus-Versionen übergeben lokale Pfade meistens als Argumente.
for arg in "$@"; do
  append_path "$arg"
done

# Fallback: ältere Nautilus-Schnittstelle über Umgebungsvariablen.
if [[ ${#SELECTED[@]} -eq 0 && -n "${NAUTILUS_SCRIPT_SELECTED_FILE_PATHS:-}" ]]; then
  while IFS= read -r line; do
    append_path "$line"
  done <<< "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS"
fi

if [[ ${#SELECTED[@]} -eq 0 && -n "${NAUTILUS_SCRIPT_SELECTED_URIS:-}" ]]; then
  while IFS= read -r line; do
    append_path "$line"
  done <<< "$NAUTILUS_SCRIPT_SELECTED_URIS"
fi

if [[ ! -x "$APP" ]]; then
  notify_error "Starter fehlt oder ist nicht ausführbar: $APP\n\nBitte im Projektordner ausführen:\nmake install-nautilus"
  exit 127
fi

# Nur existierende lokale Dateien/Ordner weiterreichen. Nicht-lokale URIs werden ignoriert.
VALID=()
for p in "${SELECTED[@]}"; do
  if [[ -e "$p" ]]; then
    VALID+=("$p")
  else
    log "IGNORIERE nicht existierenden Pfad: $p"
  fi
done

# Kein harter Fehler: Ohne Auswahl öffnet das Programm seinen normalen GUI-/Inbox-Pfad.
log "START dryrun=__DRYRUN__ args=${#VALID[@]} pwd=$PWD"

CMD=("$APP" --gui)
if [[ "__DRYRUN__" == "1" ]]; then
  CMD+=(--dry-run)
fi
CMD+=("${VALID[@]}")

# Hintergrundstart, damit Nautilus nicht blockiert. stdout/stderr gehen ins Log.
(
  log "EXEC: ${CMD[*]}"
  exec "${CMD[@]}"
) >> "$LOGFILE" 2>&1 &

disown || true
exit 0
EOF_SCRIPT
  sed -i "s/__DRYRUN__/$dry_run/g" "$target"
  chmod 0755 "$target"
}

write_nautilus_script "$SCRIPT_NORMAL" "0"
write_nautilus_script "$SCRIPT_DRYRUN" "1"

cat <<MSG
Nautilus-Integration installiert:
  $SCRIPT_NORMAL
  $SCRIPT_DRYRUN

Wrapper:
  $WRAPPER -> $APP_BIN

Logdatei:
  $STATE_DIR/nautilus.log

Jetzt Nautilus neu laden:
  nautilus -q
MSG
