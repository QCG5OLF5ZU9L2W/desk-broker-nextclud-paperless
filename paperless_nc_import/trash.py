from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


class TrashError(RuntimeError):
    pass


def move_to_trash(path: Path) -> None:
    """Move a local file to the desktop trash.

    Prefer Send2Trash because it is cross-platform and follows the desktop trash
    semantics. Fall back to gio trash on Linux-like systems if Send2Trash is not
    available.
    """
    if not path.exists():
        raise TrashError(f"Datei existiert nicht mehr und kann nicht in den Papierkorb verschoben werden: {path}")

    try:
        from send2trash import send2trash  # type: ignore

        send2trash(str(path))
        return
    except Exception as first_exc:
        gio = shutil.which("gio")
        if gio:
            try:
                subprocess.run([gio, "trash", str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                return
            except subprocess.CalledProcessError as second_exc:
                raise TrashError(
                    f"Send2Trash fehlgeschlagen ({first_exc}); gio trash fehlgeschlagen: {second_exc.stderr.strip()}"
                ) from second_exc
        raise TrashError(f"Send2Trash nicht nutzbar und gio trash nicht gefunden: {first_exc}") from first_exc
