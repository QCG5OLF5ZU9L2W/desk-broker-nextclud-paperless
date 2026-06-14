# Built-in extraction rulesets, locale `de`

Diese Dateien enthalten ausschließlich fachliche Label-Anker und Gewichte,
keine Dokumente, keine OCR-Volltexte und keine erkannten Werte.

Beispiel:

```json
{"text": "fahrzeugpreis inklusive nebenkosten", "weight": 0.96}
```

Der Wert hinter diesem Label wird lokal im Client gesucht und bleibt lokal.
Für Community-Lernen darf später nur ein reduziertes Signal wie
`amount.total <- "fahrzeugpreis inklusive nebenkosten"` übertragen werden.
