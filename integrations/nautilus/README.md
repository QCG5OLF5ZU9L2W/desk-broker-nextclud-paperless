# Nautilus-Integration

Die korrekte Installation erfolgt nicht durch Kopieren dieser Vorlagen, sondern über den Installer:

```bash
cd paperless-nc-import-py-v0.5.1
make install-nautilus
nautilus -q
```

Der Installer erzeugt:

```text
~/.local/bin/paperless-nc-import
~/.local/share/nautilus/scripts/An Paperless senden
~/.local/share/nautilus/scripts/An Paperless senden (Dry-run)
```

Warum so?

- Nautilus kennt die Python-venv nicht.
- Der Starter in `~/.local/bin` nutzt deshalb den absoluten Pfad zur Projekt-venv.
- Die Nautilus-Scripts sammeln markierte Dateien robust aus `$@`, `NAUTILUS_SCRIPT_SELECTED_FILE_PATHS` und `NAUTILUS_SCRIPT_SELECTED_URIS`.
- `file://`-URIs werden sauber in lokale Pfade dekodiert.
- Nicht-lokale URIs werden ignoriert und geloggt.
- Nautilus wird nicht blockiert; die GUI startet im Hintergrund.

Log:

```text
~/.local/state/paperless-nc-import/nautilus.log
```

Nach Updates immer erneut ausführen:

```bash
make install-nautilus
nautilus -q
```
