# macOS Finder Quick Action

Für macOS ist zunächst eine Finder Quick Action vorgesehen:

1. Automator oder Shortcuts öffnen.
2. Quick Action für Finder-Dateien erstellen.
3. Shell-Befehl ausführen:

```bash
/opt/paperless-nc-import/bin/paperless-nc-import --gui "$@"
```

Die finale Paketierung sollte später einen signierten `.app`-Wrapper bereitstellen.
