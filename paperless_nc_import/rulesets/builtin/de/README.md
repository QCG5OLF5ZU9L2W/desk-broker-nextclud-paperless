# Built-in extraction rulesets, locale `de`

Diese Dateien enthalten ausschließlich fachliche Label-Anker und Gewichte.
Sie enthalten **keine** Dokumente, **keine** OCR-Volltexte, **keine** erkannten
Werte, **keine** Dateinamen, **keine** Pfade und **keine** Paperless-/Nextcloud-IDs.

Beispiel:

```json
{"text": "rechnungsbetrag", "weight": 0.94}
```

Der Wert hinter diesem Label wird lokal im Client gesucht und bleibt lokal.
Für DSGVO-konformes Community-Lernen darf später nur ein reduziertes Signal wie
`amount.total <- "rechnungsbetrag" accepted` übertragen werden.
