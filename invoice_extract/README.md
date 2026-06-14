# invoice2data DE receipt template starter pack

Erster Template-Entwurf auf Basis der bereitgestellten Beispielbelege.

## Wichtig

- Die YAMLs sind bewusst als `draft` zu verstehen. Viele Beispielbelege sind reine Scan-/Bild-PDFs; die Regexe müssen gegen den echten OCR-Text validiert werden.
- Originalbelege gehören nicht ins Git. Ablage nur privat, z. B. `samples/private/` in `.gitignore`.
- Für Tests sollten anonymisierte OCR-Texte oder geschwärzte PDFs genutzt werden.

## Test

```bash
invoice2data \
  --template-folder templates/de \
  --exclude-built-in-templates \
  --input-reader tesseract \
  --output-format json \
  /pfad/zum/beleg.pdf
```

Bei Text-PDFs:

```bash
invoice2data \
  --template-folder templates/de \
  --exclude-built-in-templates \
  --input-reader pdfplumber \
  --debug \
  /pfad/zur/rechnung.pdf
```
