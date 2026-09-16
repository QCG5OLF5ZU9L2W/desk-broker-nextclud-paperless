#!/usr/bin/env python3
"""Per-user installer for Firefox on Windows / Debian / Ubuntu. No elevation."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

HOST = 'paperless_send_api'
EXTENSION = 'paperless-send@local'

def main():
    parser = argparse.ArgumentParser(description='Optionalen Paperless-Dateihelfer für Firefox installieren.')
    parser.add_argument('--uninstall', action='store_true', help='Nur den Dateihelfer entfernen, keine Dokumente oder Firefox-Einstellungen.')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 oder neuer erforderlich.')
    if os.name == 'nt':
        import winreg
        appdir = Path(os.environ['LOCALAPPDATA']) / 'PaperlessSendAPI'
        manifest = appdir / (HOST + '.json')
        registry = 'Software\\Mozilla\\NativeMessagingHosts\\' + HOST
    elif sys.platform.startswith('linux'):
        appdir = Path.home() / '.local' / 'share' / 'paperless-send-api'
        manifest = Path.home() / '.mozilla' / 'native-messaging-hosts' / (HOST + '.json')
    else:
        raise SystemExit('Dieser Installer unterstützt Windows, Debian und Ubuntu.')
    if args.uninstall:
        if os.name == 'nt':
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, registry)
            except FileNotFoundError:
                pass
        manifest.unlink(missing_ok=True)
        # Delete only known files, leaving all unrelated files untouched.
        for name in ('paperless_helper.py', 'launch.bat', 'launch.sh'):
            (appdir / name).unlink(missing_ok=True)
        try:
            appdir.rmdir()
        except OSError:
            pass
        print('Dateihelfer entfernt. Dokumente und Erweiterung bleiben erhalten.')
        return
    appdir.mkdir(parents=True, exist_ok=True)
    target = appdir / 'paperless_helper.py'
    shutil.copy2(Path(__file__).with_name('paperless_helper.py'), target)
    python = str(Path(sys.executable).resolve())
    if os.name == 'nt':
        launcher = appdir / 'launch.bat'
        if any(c in python + str(target) for c in '%\r\n'):
            raise SystemExit('Installationspfad darf kein Prozentzeichen oder Zeilenumbruch enthalten.')
        launcher.write_bytes(('@echo off\r\nchcp 65001 >nul\r\nsetlocal DisableDelayedExpansion\r\n"' + python + '" -u "' + str(target) + '" %*\r\n').encode('utf-8'))
    else:
        launcher = appdir / 'launch.sh'
        launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(python) + ' -u ' + shlex.quote(str(target)) + ' "$@"\n', encoding='utf-8')
        launcher.chmod(0o700)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'name': HOST, 'description': 'Paperless Send optional PDF file helper', 'path': str(launcher), 'type':'stdio', 'allowed_extensions':[EXTENSION]}, indent=2), encoding='utf-8')
    if os.name == 'nt':
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry) as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest))
    else:
        manifest.chmod(0o600)
    print('Dateihelfer installiert für den aktuellen Benutzer.')
    print('Firefox neu starten; in Paperless Send > Einstellungen den Dateihelfer aktivieren und testen.')
    if sys.platform.startswith('linux'):
        print('Grafische Dateiauswahl: python3-tk erforderlich. Firefox Snap/Flatpak benötigt zusätzlich funktionierende Native-Messaging-Portal-Unterstützung.')

if __name__ == '__main__':
    main()
