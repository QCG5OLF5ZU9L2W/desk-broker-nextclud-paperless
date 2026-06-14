from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import platform
import re
import subprocess
import time

BIRTH_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def birthtime(path: Path) -> datetime:
    stat = path.stat()
    # macOS and Windows usually expose st_birthtime.
    value = getattr(stat, "st_birthtime", None)
    if value and value > 0:
        return datetime.fromtimestamp(value).astimezone()

    if platform.system() == "Linux":
        try:
            out = subprocess.check_output(["stat", "-c", "%W", str(path)], text=True).strip()
            ts = int(out)
            if ts > 0:
                return datetime.fromtimestamp(ts).astimezone()
        except Exception:
            pass

    # Fallback: mtime is semantically less accurate but stable enough.
    return datetime.fromtimestamp(stat.st_mtime).astimezone()


def is_file_old_enough(path: Path, min_age_seconds: int) -> bool:
    if min_age_seconds <= 0:
        return True
    age = time.time() - path.stat().st_mtime
    return age >= min_age_seconds


def unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i:03d}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def birth_prefixed_path(path: Path, dt: datetime, fmt: str = "%Y-%m-%d_%H-%M-%S") -> Path:
    if BIRTH_PREFIX_RE.match(path.name):
        return path
    stamp = dt.strftime(fmt)
    return unique_path(path.with_name(f"{stamp}_{path.name}"))


def collect_input_files(args: list[str], inbox_dir: Path, pattern: str, min_age_seconds: int) -> list[Path]:
    """Collect importable input files.

    Important UX rule:
    - Explicit file arguments from Nautilus/CLI are taken as an intentional user action
      and must not be filtered by min_age_seconds. A user can deliberately import a
      just-synced PDF.
    - Directory scans and implicit inbox scans still respect min_age_seconds, because
      those are the cases where a file may still be written by scanner/Nextcloud.
    """
    candidates: list[tuple[Path, bool]] = []  # (path, explicit_file)
    if args:
        for raw in args:
            p = Path(raw).expanduser()
            if p.is_dir():
                candidates.extend((x, False) for x in sorted(p.glob(pattern)) if x.is_file())
            elif p.is_file():
                candidates.append((p, True))
    else:
        candidates.extend((x, False) for x in sorted(inbox_dir.expanduser().glob(pattern)) if x.is_file())

    seen: set[Path] = set()
    out: list[Path] = []
    for file, explicit_file in candidates:
        resolved = file.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if explicit_file or is_file_old_enough(resolved, min_age_seconds):
            out.append(resolved)
    return out


def title_from_filename(path: Path) -> str:
    name = path.stem
    name = BIRTH_PREFIX_RE.sub("", name)
    return name.replace("_", " ").strip() or path.stem
