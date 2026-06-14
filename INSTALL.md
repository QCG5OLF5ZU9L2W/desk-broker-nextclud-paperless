# Installation v0.7.6

## Systempakete Ubuntu/Debian

```bash
sudo apt update
sudo apt install \
  python3-venv python3-dev build-essential \
  libgl1 libegl1 libxkbcommon-x11-0 \
  libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
  libxcb-xfixes0 libxcb-xinput0 \
  ocrmypdf tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
  poppler-utils ghostscript qpdf unpaper pngquant
```

## Python

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .
```

## Config

```bash
mkdir -p ~/.config/paperless-nc-import
cp configs/config.example.yaml ~/.config/paperless-nc-import/config.yaml
vi ~/.config/paperless-nc-import/config.yaml
```

## Secrets für Deck

```bash
install -d -m 700 ~/.config/paperless-nc-import
cat > ~/.config/paperless-nc-import/secrets.env <<'EOF2'
NC_DECK_APP_PASSWORD_NC5ST='DEIN_NEXTCLOUD_APP_PASSWORT'
EOF2
chmod 600 ~/.config/paperless-nc-import/secrets.env
```

## Nautilus

```bash
make install-nautilus
nautilus -q
```


## v0.7.5: Paperless-Duplikate

Wenn Paperless einen Import als Duplikat erkennt und `related_document` liefert, wird das vorhandene Paperless-Dokument als Quelle der Wahrheit verwendet. Die GUI zeigt die Attribute des vorhandenen Dokuments und fragt interaktiv, ob die lokale Quelldatei in den Papierkorb verschoben werden soll. Eine Wiedervorlage/Deck-Integration kann trotzdem gegen das bereits vorhandene Paperless-Dokument laufen.


## v0.7.6: OCR-Fortschritt und Auto-Close

Zusätzliche/angepasste Config-Werte:

```yaml
ocr:
  # 0 = OCRmyPDF entscheidet selbst und nutzt typischerweise mehr verfügbare Kerne.
  # Bei zu hoher Last z.B. 2 oder 4 setzen.
  jobs: 0

gui:
  close_after_success: true
  close_after_seconds: 2
```

Der OCR-Fortschritt ist ein Stufen-/Livelog-Fortschritt. OCRmyPDF liefert je nach Version keine stabile maschinenlesbare Prozentanzeige, deshalb zeigt die GUI Statuszeilen und einen Näherungsfortschritt statt falscher Präzision.
