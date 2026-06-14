from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import hashlib
import json
import os


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_extractions (
    global_document_id TEXT PRIMARY KEY,
    paperless_document_id INTEGER,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    document_date DATE,
    due_date DATE,
    amount_total DOUBLE,
    amount_vat DOUBLE,
    amount_net DOUBLE,
    currency TEXT,
    iban TEXT,
    extractor TEXT,
    confidence DOUBLE,
    review_status TEXT,
    source_path_hash TEXT,
    metadata_json TEXT
);
"""


@dataclass(slots=True)
class AnalyticsDocumentRecord:
    """Privacy-aware analytics row for local DuckDB/Metabase use.

    The record intentionally does not carry OCR full text or local paths.  If a
    caller wants to relate rows to local files, it should pass a one-way
    ``source_path_hash`` and keep the raw path outside the analytics database.
    """

    global_document_id: str
    paperless_document_id: int | None = None
    document_date: str | None = None
    due_date: str | None = None
    amount_total: float | None = None
    amount_vat: float | None = None
    amount_net: float | None = None
    currency: str = "EUR"
    iban: str | None = None
    extractor: str = ""
    confidence: float | None = None
    review_status: str = "draft"
    source_path_hash: str | None = None
    metadata: dict[str, Any] | None = None


class DuckDBAnalyticsStore:
    """Optional local DuckDB sink for Metabase and bookkeeping dashboards.

    duckdb is intentionally optional.  Importing this module is cheap; the
    dependency is only required when the store is opened.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = _expand(path)

    def connect(self):
        try:
            import duckdb  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency branch
            raise RuntimeError(
                "DuckDB support is optional. Install with: pip install '.[analytics]'"
            ) from exc
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(self.path))
        con.execute(SCHEMA_SQL)
        return con

    def upsert_document(self, record: AnalyticsDocumentRecord) -> None:
        metadata_json = json.dumps(record.metadata or {}, ensure_ascii=False, sort_keys=True)
        with self.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO document_extractions (
                    global_document_id,
                    paperless_document_id,
                    document_date,
                    due_date,
                    amount_total,
                    amount_vat,
                    amount_net,
                    currency,
                    iban,
                    extractor,
                    confidence,
                    review_status,
                    source_path_hash,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    record.global_document_id,
                    record.paperless_document_id,
                    record.document_date,
                    record.due_date,
                    record.amount_total,
                    record.amount_vat,
                    record.amount_net,
                    record.currency,
                    record.iban,
                    record.extractor,
                    record.confidence,
                    record.review_status,
                    record.source_path_hash,
                    metadata_json,
                ],
            )

    def export_record_dict(self, record: AnalyticsDocumentRecord) -> dict[str, Any]:
        data = asdict(record)
        data["metadata_json"] = json.dumps(data.pop("metadata") or {}, ensure_ascii=False, sort_keys=True)
        return data



def source_path_hash(path: str | Path) -> str:
    """Return a stable local hash for a path without exposing the path itself.

    This is for the local analytics database only. Do not use it for community
    learning payloads, because hashes of small private namespaces can still be
    brute-forced.
    """
    raw = str(_expand(path))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _expand(path: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(path))))
