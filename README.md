# Desk Broker – Nextcloud ↔ Paperless

Desk Broker ist ein lokales Import- und Workflow-Werkzeug für Dokumente, die aus Nextcloud nach Paperless-ngx übernommen werden sollen.

Ziel ist nicht, Paperless zu ersetzen. Paperless bleibt die Quelle der Wahrheit für Archivierung, OCR, Metadaten und Suche. Desk Broker ergänzt den Prozess um eine lokale Vorprüfung, Custom-Field-Befüllung, Nextcloud-Rückverweise und perspektivisch Deck-/E-Akten-Workflows.

## Funktionsumfang

* Import von lokalen oder Nextcloud-synchronisierten Dateien nach Paperless-ngx
* GUI zur Sichtprüfung vor dem Import
* Anzeige von PDF/Text/OCR-Inhalten
* Unterstützung von Paperless Custom Fields
* Automatische Vorbelegung ausgewählter Custom Fields
* IBAN-Erkennung mit Prüfziffervalidierung
* Nextcloud-Rückverweise auf Ursprungspfade
* Papierkorb-/Aufräumlogik nach bewusster Nutzerentscheidung
* Nautilus-Integration für GNOME/Linux
* Vorbereitung für Nextcloud Deck als Workflow-/E-Akten-Cockpit
* Anlegen von Arbeitsvorräten aus Wiedervorlagen in Nextcloud Deck

## Grundidee

```text
Nextcloud / lokaler Ordner
        ↓
Desk Broker GUI
        ↓
OCR / Textanalyse / Custom Fields
        ↓
Paperless-ngx
        ↓
optional: Nextcloud Deck / E-Akte / Wiedervorlage
```

Paperless bleibt das Archiv.
Nextcloud bleibt die Arbeits- und Sync-Struktur.
Deck kann später Vorgänge, Fristen und Bearbeitungsstände abbilden.

## Installation aus Git

Voraussetzungen unter Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  make \
  rsync \
  poppler-utils \
  gir1.2-gtk-3.0 \
  python3-gi
```

Projekt klonen:

```bash
cd ~/Documents
git clone git@github.com:QCG5OLF5ZU9L2W/desk-broker-nextclud-paperless.git
cd desk-broker-nextclud-paperless
```

Falls SSH noch nicht eingerichtet ist, alternativ:

```bash
git clone https://github.com/QCG5OLF5ZU9L2W/desk-broker-nextclud-paperless.git
```

Virtuelle Python-Umgebung erstellen:

```bash
python3 -m venv .venv
. .venv/bin/activate

pip install -U pip
pip install -e .
```

Installation prüfen:

```bash
python3 -m compileall paperless_nc_import
PYTHONPATH=. pytest -q
```

GUI starten:

```bash
paperless-nc-import --gui
```

Systemprüfung:

```bash
paperless-nc-import --doctor
```

## Nautilus-Integration installieren

```bash
make install-nautilus
nautilus -q
```

Danach können Dateien im Dateimanager über das Kontextmenü an Desk Broker übergeben werden.

## Konfiguration

Die Nutzerkonfiguration liegt standardmäßig unter:

```bash
~/.config/paperless-nc-import/config.yaml
```

Ein Beispiel befindet sich unter:

```bash
configs/config.example.yaml
```

Minimalstruktur:

```yaml
paperless:
  url: "https://paperless.example.tld"
  token: "PAPERLESS_API_TOKEN"

nextcloud:
  base_url: "https://cloud.example.tld"
  local_root: "/home/user/Nextcloud"

custom:
  custom_field_nextcloud_path_id: "14"
  custom_field_local_path_id: ""
  field_deck_card_url_id: null
  field_deck_card_id_id: null
  field_global_document_id_id: null
  field_process_id_id: null
```

## Custom Fields

Desk Broker nutzt Paperless Custom Fields möglichst über IDs. Dadurch bleibt die Zuordnung stabil, auch wenn Feldnamen später geändert werden.

Beispiel:

```yaml
custom:
  custom_field_nextcloud_path_id: "14"
```

Die GUI zeigt Paperless-Felder typgerecht an, zum Beispiel:

```text
Rechnungsbetrag [#3, monetary]
IBAN [#6, string]
Wiedervorlage [#2, date]
```

## Automatische Vorbelegung

Desk Broker kann Werte aus OCR- oder PDF-Texten vorschlagen. Die Werte werden zunächst nur vorbelegt. Der Nutzer entscheidet weiterhin bewusst, ob das Custom Field übernommen wird.

Beispiel:

```text
Fahrzeugpreis inklusive Nebenkosten: 15900,00 Euro
```

kann als Kandidat für:

```text
Rechnungsbetrag / amount.total
```

verwendet werden.

Die langfristige Architektur sieht ein rollenbasiertes Extraktionssystem vor:

```text
Paperless Custom Field #3
        ↓
Rolle: amount.total
        ↓
Extractor sucht passende Beträge
        ↓
GUI schlägt Wert vor
        ↓
Nutzer bestätigt oder korrigiert
```

## Community-Lernen

Geplant ist ein datensparsames Community-Lernen für Extraktionsregeln.

Es werden dabei keine Dokumente, keine OCR-Volltexte, keine Beträge, keine IBANs, keine Pfade und keine IDs übertragen.

Zulässiges Lernsignal wäre zum Beispiel:

```json
{
  "locale": "de",
  "field_role": "amount.total",
  "field_type": "monetary",
  "label_normalized": "fahrzeugpreis inklusive nebenkosten",
  "result": "accepted"
}
```

Nicht übertragen werden:

* Beträge
* Dokumente
* OCR-Texte
* Dateinamen
* Nextcloud-Pfade
* Paperless-IDs
* Deck-IDs
* IBANs
* Namen
* Adressen
* Aktenzeichen

Community-Lernen ist opt-in und soll nur nach ausdrücklicher Zustimmung erfolgen.

## Tests

```bash
python3 -m compileall paperless_nc_import
PYTHONPATH=. pytest -q
```

## Entwicklung

Editable Installation:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .
```

Nautilus neu installieren:

```bash
make install-nautilus
nautilus -q
```

## Projektstatus

Das Projekt befindet sich im Aufbau. Die aktuelle Linie ist:

```text
v0.7.x  GUI, Paperless-Import, Custom Fields, Nextcloud-Rückverweise
v0.8.x  rollenbasierte Extraktion, lokales Lernen
v0.9.x  Community-Rulesets, Deck-/E-Akten-Anbindung
```

## Lizenz

Siehe `LICENSE`.

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
