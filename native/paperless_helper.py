#!/usr/bin/env python3
"""Optional Firefox file bridge. No network, tokens, config, or document logging.
Only PDFs opened in the current native connection can subsequently be deleted.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import struct
import sys
from urllib.parse import unquote, urlsplit

VERSION = '2.0.0'
EXTENSION = 'paperless-send@local'
MAX_BYTES = 100 * 1024 * 1024
CHUNK = 256 * 1024


def parse_path(value, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    text = str(value)
    if text.lower().startswith('file:'):
        u = urlsplit(text)
        if u.query or u.fragment:
            raise ValueError('Lokale Datei-URL darf keine Suchparameter oder Fragmente enthalten.')
        text = unquote(u.path)
        if windows:
            if u.netloc and u.netloc.lower() != 'localhost':
                text = '//' + u.netloc + text
            elif len(text) > 3 and text[0] == '/' and text[2] == ':':
                text = text[1:]
            text = text.replace('/', '\\')
        elif u.netloc and u.netloc.lower() != 'localhost':
            raise ValueError('Unter Linux eine lokal eingehängte Datei auswählen.')
    if '\x00' in text:
        raise ValueError('Ungültiger Dateipfad.')
    return text


def fingerprint(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def inspect(path):
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
        raise ValueError('Nur reguläre PDF-Dateien bis 100 MiB sind zulässig.')
    h = hashlib.sha256()
    with path.open('rb') as f:
        if b'%PDF-' not in f.read(1024):
            raise ValueError('Die ausgewählte Datei ist keine PDF.')
        f.seek(0)
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
        after = os.fstat(f.fileno())
    if fingerprint(before) != fingerprint(after) or fingerprint(path.stat()) != fingerprint(after):
        raise ValueError('Datei wurde während des Lesens verändert.')
    return h.hexdigest(), fingerprint(after)


class Host:
    def __init__(self):
        self.files = {}

    def dispatch(self, msg):
        action = msg.get('action')
        if action == 'ping':
            return {'version': VERSION, 'platform': sys.platform}
        if action in ('open', 'choose'):
            if action == 'choose':
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes('-topmost', True)
                    try:
                        value = filedialog.askopenfilename(title='PDF für Paperless auswählen', filetypes=[('PDF-Dokumente', '*.pdf'), ('Alle Dateien', '*')])
                    finally:
                        root.destroy()
                except Exception:
                    raise ValueError('Dateiauswahl nicht verfügbar. Unter Debian/Ubuntu python3-tk installieren oder die lokale PDF im Firefox öffnen.')
                if not value:
                    return {'cancelled': True}
            else:
                value = msg.get('path', '')
            path = Path(parse_path(value)).expanduser()
            if not path.is_absolute():
                raise ValueError('Ein absoluter Dateipfad ist erforderlich.')
            # Pin the resolved target. Never delete through a mutable symlink path.
            path = path.resolve(strict=True)
            digest, stamp = inspect(path)
            ref = secrets.token_urlsafe(32)
            self.files[ref] = {'path': path, 'digest': digest, 'stamp': stamp}
            return {'ref': ref, 'filename': path.name, 'path': str(path), 'size': stamp[2], 'sha256': digest}
        if action not in ('read', 'delete', 'release'):
            raise ValueError('Unbekannte Aktion.')
        ref = msg.get('ref')
        entry = self.files.get(ref)
        if not entry:
            raise ValueError('Datei wurde in dieser Verbindung nicht geöffnet.')
        if action == 'release':
            del self.files[ref]
            return {}
        path = entry['path']
        if path.is_symlink() or fingerprint(path.stat()) != entry['stamp']:
            raise ValueError('Originaldatei wurde verändert oder ersetzt. Sie wird nicht gelöscht.')
        if action == 'read':
            offset = msg.get('offset')
            if type(offset) is not int or not 0 <= offset < entry['stamp'][2]:
                raise ValueError('Ungültiger Leseoffset.')
            with path.open('rb') as f:
                if fingerprint(os.fstat(f.fileno())) != entry['stamp']:
                    raise ValueError('Datei wurde ersetzt.')
                f.seek(offset)
                data = f.read(CHUNK)
            return {'data': base64.b64encode(data).decode('ascii')}
        if msg.get('sha256') != entry['digest']:
            raise ValueError('Prüfsumme stimmt nicht mit der übertragenen Datei überein.')
        digest, stamp = inspect(path)
        if digest != entry['digest'] or stamp != entry['stamp']:
            raise ValueError('Originaldatei wurde verändert. Sie wird nicht gelöscht.')
        # The trusted extension invokes delete only after SUCCESS + document lookup.
        path.unlink()
        del self.files[ref]
        return {'deleted': True}


def read_exact(stream, size):
    parts = bytearray()
    while len(parts) < size:
        chunk = stream.read(size - len(parts))
        if not chunk:
            if not parts:
                return None
            raise EOFError('Unvollständige Nachricht.')
        parts.extend(chunk)
    return bytes(parts)


def serve(inp, out):
    host = Host()
    while True:
        header = read_exact(inp, 4)
        if header is None:
            return
        size = struct.unpack('=I', header)[0]
        if not 0 < size <= 1024 * 1024:
            return
        body = read_exact(inp, size)
        if body is None:
            return
        request_id = None
        try:
            msg = json.loads(body)
            if not isinstance(msg, dict):
                raise ValueError('Ungültige Nachricht.')
            request_id = msg.get('id')
            result = {'id': request_id, 'ok': True, **host.dispatch(msg)}
        except (ValueError, OSError, KeyError) as exc:
            result = {'id': request_id, 'ok': False, 'error': str(exc)}
        encoded = json.dumps(result, ensure_ascii=False).encode('utf-8')
        out.write(struct.pack('=I', len(encoded)))
        out.write(encoded)
        out.flush()


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[2] != EXTENSION:
        sys.exit(1)
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer)
    except (EOFError, BrokenPipeError):
        pass
