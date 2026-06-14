# Installation

Diese Anleitung installiert Desk Broker aus Git in eine lokale Python-Umgebung. Die Installation verändert keine System-Python-Pakete.

## Voraussetzungen Debian/Ubuntu

```bash
sudo apt update
sudo apt install -y \
  git \
  make \
  rsync \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  libgl1 \
  libegl1 \
  libxkbcommon-x11-0 \
  libxcb-cursor0 \
  libxcb-icccm4 \
  libxcb-image0 \
  libxcb-keysyms1 \
  libxcb-randr0 \
  libxcb-render-util0 \
  libxcb-shape0 \
  libxcb-xinerama0 \
  libxcb-xfixes0 \
  libxcb-xinput0 \
  ocrmypdf \
  tesseract-ocr \
  tesseract-ocr-deu \
  tesseract-ocr-eng \
  poppler-utils \
  ghostscript \
  qpdf \
  unpaper \
  pngquant
```

## Installation aus Git

```bash
bash scripts/install-from-git.sh
```

Oder manuell:

```bash
git clone git@github.com:QCG5OLF5ZU9L2W/desk-broker-nextclud-paperless.git
cd desk-broker-nextclud-paperless
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .
python -m compileall paperless_nc_import
PYTHONPATH=. pytest -q
```

Falls SSH nicht eingerichtet ist:

```bash
git clone https://github.com/QCG5OLF5ZU9L2W/desk-broker-nextclud-paperless.git
```

## Optionale Extraktions-Backends

Structured invoices und invoice2data:

```bash
. .venv/bin/activate
pip install -e '.[invoice]'
```

DuckDB/Metabase-Sink:

```bash
. .venv/bin/activate
pip install -e '.[analytics]'
```

Alles zusammen ohne schweres Layout-OCR:

```bash
. .venv/bin/activate
pip install -e '.[invoice,analytics]'
```

## Konfiguration

```bash
mkdir -p ~/.config/paperless-nc-import
cp configs/config.example.yaml ~/.config/paperless-nc-import/config.yaml
vi ~/.config/paperless-nc-import/config.yaml
```

Wichtige Bereiche:

```yaml
paperless:
  url: "https://paperless.example.tld"
  token: "CHANGE_ME"

extraction:
  enabled: true
  locale: "de"
  field_roles:
    "3": "amount.total"
    "20": "date.invoice"
    "21": "date.due"
    "6": "bank.iban"
```

Die Nummern sind die IDs der Paperless-Custom-Fields.

## Deck-Secrets

App-Passwörter gehören nicht in `config.yaml`. Stattdessen:

```bash
install -d -m 700 ~/.config/paperless-nc-import
cat > ~/.config/paperless-nc-import/secrets.env <<'EOF'
NC_DECK_APP_PASSWORD_NC5ST='DEIN_NEXTCLOUD_APP_PASSWORT'
EOF
chmod 600 ~/.config/paperless-nc-import/secrets.env
```

## Nautilus

```bash
make install-nautilus
nautilus -q
```

## Prüfung

```bash
. .venv/bin/activate
paperless-nc-import --doctor --startup-log --no-cache
python -m compileall paperless_nc_import
PYTHONPATH=. pytest -q
python scripts/validate_rulesets.py paperless_nc_import/rulesets/builtin
```

GUI-Test:

```bash
paperless-nc-import --startup-log --dry-run --gui /pfad/zur/datei.pdf
```

## Patch einspielen

Patches werden nicht manuell mit wechselnden `-p`-Stufen eingespielt. Verwende:

```bash
scripts/apply-extractor-adapter-patch.sh /pfad/zum/patch.patch
```

Das Skript:

- prüft das Git-Repo,
- legt einen Arbeitsbranch an,
- sichert einen unsauberen Arbeitsbaum als Diff und Stash,
- prüft den Patch trocken,
- installiert die venv neu,
- führt Tests und Ruleset-Validator aus,
- committed und pushed optional.

Standardmäßig wird nicht automatisch gepusht. Für Push:

```bash
PUSH=1 scripts/apply-extractor-adapter-patch.sh /pfad/zum/patch.patch
```

## Optional: PaddleOCR sidecar

For difficult scans, install the optional PaddleOCR sidecar:

```bash
scripts/install-paddleocr-sidecar.sh
```

Then enable it in `~/.config/paperless-nc-import/config.yaml`.

## Optional: PaddleOCR layout extraction

For difficult scans, install the PaddleOCR sidecar and pre-cache the document before opening it in the GUI:

```bash
scripts/install-paddleocr-sidecar.sh
scripts/precache-paddleocr.sh /path/to/document.pdf
paperless-nc-import --gui /path/to/document.pdf
```

The sidecar is local-only. It produces OCR tokens and layout boxes for the extractor chain.
