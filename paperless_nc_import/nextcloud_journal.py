from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


def _connect_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=1)


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [str(r[0]) for r in rows]


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(r[1]) for r in rows]


def lookup_journal(journal: Path | None, relative_path: str) -> dict[str, str]:
    if not journal or not journal.exists():
        return {}
    rel = relative_path.lstrip("/")
    variants = {rel, "/" + rel, rel.replace("\\", "/"), ("/" + rel).replace("\\", "/")}
    try:
        with _connect_ro(journal) as conn:
            for table in _tables(conn):
                cols = _columns(conn, table)
                lower = {c.lower(): c for c in cols}
                path_col = lower.get("path") or lower.get("filepath") or lower.get("file")
                if not path_col:
                    continue
                fileid_col = lower.get("fileid") or lower.get("file_id") or lower.get("remoteid")
                etag_col = lower.get("etag") or lower.get("getetag")
                ocid_col = lower.get("ocid") or lower.get("oc_id")
                wanted_cols = [path_col]
                for col in [fileid_col, etag_col, ocid_col]:
                    if col and col not in wanted_cols:
                        wanted_cols.append(col)
                sql = f"SELECT {', '.join(wanted_cols)} FROM {table} WHERE {path_col} IN ({', '.join(['?'] * len(variants))}) LIMIT 1"
                try:
                    row = conn.execute(sql, tuple(variants)).fetchone()
                except sqlite3.DatabaseError:
                    continue
                if not row:
                    # Fallback: case-insensitive tail match, bounded.
                    try:
                        rows = conn.execute(f"SELECT {', '.join(wanted_cols)} FROM {table} LIMIT 50000").fetchall()
                    except sqlite3.DatabaseError:
                        continue
                    row = next((r for r in rows if str(r[0]).lstrip("/").casefold() == rel.casefold()), None)
                if row:
                    data = dict(zip(wanted_cols, row, strict=False))
                    return {
                        "file_id": str(data.get(fileid_col or "", "") or ""),
                        "etag": str(data.get(etag_col or "", "") or ""),
                        "oc_id": str(data.get(ocid_col or "", "") or ""),
                    }
    except Exception:
        return {}
    return {}
