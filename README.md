# Desk Broker – Nextcloud ↔ Paperless-ngx

Desk Broker ist ein lokaler Dokumenten-Broker für Arbeitsdateien aus Nextcloud und lokalen Ordnern. Er führt Dokumente kontrolliert nach Paperless-ngx, zeigt sie vor dem Import in einer GUI an, unterstützt OCR/Review, befüllt Paperless-Custom-Fields und bereitet Workflow-Integrationen wie Nextcloud Deck und lokale Auswertung mit DuckDB/Metabase vor.

Paperless bleibt die Quelle der Wahrheit für Archiv, OCR-Index, Dokument-ID, Suche und Metadaten. Desk Broker ist die Arbeits- und Vermittlungsschicht davor.

## Zielbild

```text
Nextcloud / lokaler Ordner
        ↓
Desk Broker GUI
        ↓
OCR/Text/strukturierte Extraktion
        ↓
Review + Paperless-Custom-Fields
        ↓
Paperless-ngx
        ↓
optional: Deck / E-Akte / DuckDB / Metabase
```

## Funktionen

- Import lokaler oder Nextcloud-synchronisierter Dateien nach Paperless-ngx
- PySide6-GUI mit PDF-/Textvorschau und Paperless-Metadaten
- OCR über OCRmyPDF/Tesseract mit Sidecar-Text und Fortschrittsanzeige
- Paperless-Custom-Fields mit ID-basiertem Mapping
- Rollenbasierte Vorbelegung von Feldern wie Rechnungsbetrag, Belegdatum, Fälligkeit und IBAN
- Optionale Extraktionsadapter für strukturierte Rechnungen und `invoice2data`
- Nextcloud-Rückverweise und Sidecar-Dateien
- Vorbereitung für Nextcloud Deck als Wiedervorlage-/E-Akten-Cockpit
- Optionaler DuckDB-Sink für lokale Auswertung mit Metabase
- DSGVO-sparsames Community-Learning-Konzept für Label-Anker, nicht für Werte

## Extraktionsarchitektur

Desk Broker pflegt keine benutzerspezifischen Regex-Regeln für Rechnungen in der Nutzer-Config. Die Nutzer-Config ordnet nur lokale Paperless-Custom-Field-IDs stabilen fachlichen Rollen zu:

```yaml
extraction:
  enabled: true
  locale: "de"
  infer_roles_from_field_names: true
  field_roles:
    "3": "amount.total"
    "20": "date.invoice"
    "21": "date.due"
    "6": "bank.iban"
```

Die eigentliche Erkennung läuft über Adapter:

1. **StructuredInvoiceExtractor** – ZUGFeRD/Factur-X/XRechnung, wenn strukturierte Daten vorhanden sind.
2. **Invoice2DataExtractor** – templatebasierte PDF-Rechnungserkennung mit `invoice2data`, wenn installiert und passend.
3. **GenericTextExtractor** – generischer Fallback für Text/OCR mit Rulesets, Datumsparsern, IBAN-Prüfung und konservativem Scoring.

Bei niedriger Confidence wird lieber nichts vorbelegt als ein falscher Wert.

## Rulesets

Projekt-Rulesets liegen unter:

```text
paperless_nc_import/rulesets/builtin/de/
```

Sie enthalten nur fachliche Label-Anker und Gewichte, zum Beispiel:

```json
{
  "role": "amount.total",
  "labels": [
    {"text": "rechnungsbetrag", "weight": 0.96, "kind": "strong_total"},
    {"text": "zu zahlen", "weight": 0.95, "kind": "strong_total"},
    {"text": "kartenzahlung", "weight": 0.72, "kind": "payment_confirmation"}
  ]
}
```

Rulesets dürfen keine Beträge, keine OCR-Ausschnitte, keine Dateinamen, keine Pfade, keine IDs und keine personenbezogenen Daten enthalten. Der Validator prüft diese Datenschutzgrenzen:

```bash
python scripts/validate_rulesets.py paperless_nc_import/rulesets/builtin
```

## DSGVO-konformes Community-Learning

Community-Learning ist vorbereitet, aber standardmäßig deaktiviert.

Zulässig ist nur ein reduziertes Lernsignal wie:

```json
{
  "locale": "de",
  "field_role": "amount.total",
  "field_type": "monetary",
  "label_normalized": "rechnungsbetrag",
  "result": "accepted"
}
```

Nicht übertragen werden dürfen:

- Beträge
- Datenwerte
- Dokumente
- OCR-Volltexte
- Dateinamen
- lokale oder Nextcloud-Pfade
- Paperless-/Nextcloud-/Deck-IDs
- IBAN-Werte
- Namen, Adressen, Aktenzeichen oder sonstige personenbezogene Inhalte

Ein Upload von Lernsignalen darf nur nach ausdrücklicher Einwilligung erfolgen.

## DuckDB / Metabase

Der optionale DuckDB-Sink ist für lokale Auswertung gedacht. Er speichert keine OCR-Volltexte und keine lokalen Pfade, sondern nur strukturierte Review-/Extraktionswerte.

```yaml
analytics:
  duckdb:
    enabled: false
    path: "~/.local/share/paperless-nc-import/analytics.duckdb"
```

Installation der optionalen DuckDB-Unterstützung:

```bash
pip install -e '.[analytics]'
```

Metabase kann anschließend über einen DuckDB-Connector auf die lokale Datenbank zugreifen.

## Installation

Siehe [INSTALL.md](INSTALL.md).

Kurzfassung für Debian/Ubuntu:

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

Nautilus-Integration:

```bash
make install-nautilus
nautilus -q
```

## Git-Arbeitsweise

Für Änderungen immer einen Branch verwenden:

```bash
git checkout -b feature/name-der-aenderung
python -m compileall paperless_nc_import
PYTHONPATH=. pytest -q
git add .
git commit -m "Kurze fachliche Beschreibung"
git push -u origin feature/name-der-aenderung
```

Patches werden mit dem Skript `scripts/apply-extractor-adapter-patch.sh` eingespielt. Das Skript legt bei einem unsauberen Arbeitsbaum vorher ein Backup-Diff an und arbeitet auf einem eigenen Branch.

## Tests

```bash
python -m compileall paperless_nc_import
PYTHONPATH=. pytest -q
python scripts/validate_rulesets.py paperless_nc_import/rulesets/builtin
```

## Projektstatus

Das Projekt ist im Aufbau. Die aktuelle Linie ist:

```text
v0.7.x  Desktop-GUI, Paperless-Import, OCR, Nextcloud-Rückverweise
v0.8.x  Extractor-Adapter, Rollenmodell, invoice2data, DuckDB-Sink
v0.9.x  Deck-/E-Akten-Workflow, lokales Lernen, Community-Rulesets
```

## Lizenz

Siehe [LICENSE](LICENSE).
