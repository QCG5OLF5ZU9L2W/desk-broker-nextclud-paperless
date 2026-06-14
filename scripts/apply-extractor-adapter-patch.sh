#!/usr/bin/env bash
set -euo pipefail

PATCH_PATH="${1:-}"
REPO="${REPO:-$(pwd)}"
BRANCH="${BRANCH:-feature/extractor-adapter-architecture}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Add extractor adapter architecture}"
PUSH="${PUSH:-0}"
AUTO_STASH="${AUTO_STASH:-1}"
EXTRAS="${EXTRAS:-}"

fail() { printf '\nABBRUCH: %s\n' "$*" >&2; exit 1; }
say() { printf '\n== %s ==\n' "$*"; }

[ -n "$PATCH_PATH" ] || fail "Aufruf: $0 /pfad/zum/patch.patch"
PATCH_PATH="$(readlink -f "$PATCH_PATH")"
[ -f "$PATCH_PATH" ] || fail "Patch nicht gefunden: $PATCH_PATH"

cd "$REPO" || fail "Repo nicht gefunden: $REPO"
[ -d .git ] || fail "Kein Git-Repo: $REPO"
[ -f pyproject.toml ] || fail "pyproject.toml fehlt. Falscher Ordner?"
[ -d paperless_nc_import ] || fail "paperless_nc_import fehlt. Falscher Ordner?"

say "Repo"
pwd
git branch --show-current || true
git status --short

if [ -n "$(git status --porcelain)" ]; then
  if [ "$AUTO_STASH" != "1" ]; then
    fail "Arbeitsbaum ist nicht sauber. Setze AUTO_STASH=1 oder räume vorher auf."
  fi
  say "Arbeitsstand sichern"
  mkdir -p .patch-backups
  BACKUP_DIFF=".patch-backups/prepatch-$(date +%Y%m%d-%H%M%S).diff"
  git diff > "$BACKUP_DIFF" || true
  git diff --cached >> "$BACKUP_DIFF" || true
  git stash push -u -m "prepatch $(date +%Y%m%d-%H%M%S)" || fail "Stash fehlgeschlagen."
  echo "Backup-Diff: $BACKUP_DIFF"
fi

say "Branch"
if git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
  git checkout "$BRANCH"
else
  git checkout -b "$BRANCH"
fi

say "Patch prüfen"
if git apply --check "$PATCH_PATH" >/tmp/desk-broker-git-apply.log 2>&1; then
  git apply "$PATCH_PATH"
elif patch --dry-run -p1 < "$PATCH_PATH" >/tmp/desk-broker-patch.log 2>&1; then
  patch -p1 < "$PATCH_PATH"
else
  echo "git apply:" >&2
  cat /tmp/desk-broker-git-apply.log >&2 || true
  echo >&2
  echo "patch -p1:" >&2
  cat /tmp/desk-broker-patch.log >&2 || true
  fail "Patch passt nicht auf diesen Stand."
fi

say "venv und Installation"
rm -rf .venv
python3 -m venv .venv
PY=".venv/bin/python"
"$PY" -m pip install -U pip
if [ -n "$EXTRAS" ]; then
  if ! "$PY" -m pip install -e ".[${EXTRAS}]"; then
    echo "WARNUNG: Extras konnten nicht installiert werden; installiere Basis ohne Extras."
    "$PY" -m pip install -e .
  fi
else
  "$PY" -m pip install -e .
fi
"$PY" -m pip install pytest

say "Tests"
"$PY" -m compileall paperless_nc_import
PYTHONPATH=. "$PY" -m pytest -q
if [ -f scripts/validate_rulesets.py ]; then
  "$PY" scripts/validate_rulesets.py paperless_nc_import/rulesets/builtin
fi

say "Commit"
git config user.name >/dev/null 2>&1 || git config user.name "Frank Fünfstück"
git config user.email >/dev/null 2>&1 || git config user.email "frank@fuenfstuecks.de"
git status --short

git add .
if git diff --cached --quiet; then
  echo "Keine Änderungen zu committen."
else
  git commit -m "$COMMIT_MESSAGE"
fi

if [ "$PUSH" = "1" ]; then
  say "Push"
  git remote set-url origin git@github.com:QCG5OLF5ZU9L2W/desk-broker-nextclud-paperless.git
  git push -u origin "$BRANCH"
else
  say "Kein Push"
  echo "Push später mit: git push -u origin '$BRANCH'"
fi

say "Fertig"
echo "GUI neu starten:"
echo "  . .venv/bin/activate"
echo "  paperless-nc-import --gui"
