# paperless-nc-import v0.7.6

Python/PySide6 Import-GUI für lokale Nextcloud-Dateien nach Paperless-ngx mit OCR, Paperless-Metadaten, Nextcloud-Rückverweis und optionaler Nextcloud-Deck-Wiedervorlage.

## Neu in v0.7.6

- OCR-Fortschrittsanzeige in der GUI: Status, Fortschrittsbalken und laufende OCRmyPDF-Ausgabe.
- Automatische OCR während des Imports meldet den Fortschritt ebenfalls in die GUI.
- OCR-CPU-Nutzung besser steuerbar: `ocr.jobs: 0` lässt OCRmyPDF automatisch/mehr Kerne nutzen; feste Werte begrenzen die Last.
- Optionales automatisches Schließen nach vollständig abgeschlossenem Import: `gui.close_after_success`, `gui.close_after_seconds`.

## Neu in v0.7.5

- Paperless-Rücklinkfelder: Nach erfolgreichem Import können Deck-Karten-URL, Deck-Karten-ID, globale Dokument-ID und Vorgangs-ID in Paperless-Custom-Fields geschrieben werden.
- Globale Dokument-ID: standardmäßig `urn:paperless:{paperless_host}:document:{paperless_document_id}`.
- Vorgangs-ID: standardmäßig gleich globale Dokument-ID; per Template anpassbar.
- Deck-Beschreibung enthält automatisch einen stabilen Markerblock mit Paperless-Dokument-ID, globaler Dokument-ID und Vorgangs-ID.
- Deck-Sektion in der GUI erscheint nur noch, wenn ein gültiges Wiedervorlage-Custom-Field gesetzt wurde.
- Sidecar JSON/Markdown enthält globale Dokument-ID, Vorgangs-ID und den Status der Paperless-Rücklinkaktualisierung.

## Relevante Config-Erweiterung

```yaml
custom:
  field_deck_card_url_id: null
  field_deck_card_id_id: null
  field_global_document_id_id: null
  field_process_id_id: null

  global_document_id_template: "urn:paperless:{paperless_host}:document:{paperless_document_id}"
  process_id_template: "{global_document_id}"

  require_backlink_update_for_trash: false
```

Die Feld-IDs müssen die IDs deiner Paperless-Custom-Fields sein. Wenn ein Feld `null` bleibt, wird es nicht geschrieben.

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .
```

Nautilus:

```bash
make install-nautilus
nautilus -q
```

## Test

```bash
paperless-nc-import --doctor --startup-log --no-cache
paperless-nc-import --startup-log --dry-run --gui /pfad/zur/datei.pdf
```


## v0.7.5: Paperless-Duplikate

Wenn Paperless einen Import als Duplikat erkennt und `related_document` liefert, wird das vorhandene Paperless-Dokument als Quelle der Wahrheit verwendet. Die GUI zeigt die Attribute des vorhandenen Dokuments und fragt interaktiv, ob die lokale Quelldatei in den Papierkorb verschoben werden soll. Eine Wiedervorlage/Deck-Integration kann trotzdem gegen das bereits vorhandene Paperless-Dokument laufen.
