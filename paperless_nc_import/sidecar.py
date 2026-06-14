from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .models import FileInfo, ImportResult, ImportSelection


def _safe_dt(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def write_sidecars(
    *,
    link_dir_name: str,
    file_info: FileInfo,
    selection: ImportSelection,
    result: ImportResult,
    paperless_url: str = "",
    write_json: bool = True,
    write_markdown: bool = True,
) -> tuple[Path | None, Path | None]:
    parent = file_info.current_path.parent / link_dir_name
    parent.mkdir(parents=True, exist_ok=True)
    base = parent / f"{file_info.current_path.name}.paperless"

    nc = file_info.nextcloud
    payload = {
        "created": datetime.now(timezone.utc).isoformat(),
        "local_path": str(file_info.current_path),
        "original_path": str(file_info.original_path),
        "sha256": file_info.sha256,
        "birthtime": file_info.birthtime.isoformat(),
        "paperless_task_id": result.task_id,
        "paperless_task_status": result.task_status,
        "paperless_task_success": result.task_success,
        "paperless_task_failed": result.task_failed,
        "paperless_task_response": result.task_response,
        "paperless_document_id": result.document_id,
        "paperless_document_url": paperless_url,
        "paperless_duplicate_detected": result.duplicate_detected,
        "paperless_duplicate_document_id": result.duplicate_document_id,
        "paperless_duplicate_reason": result.duplicate_reason,
        "paperless_existing_document": result.existing_document,
        "global_document_id": result.global_document_id,
        "process_id": result.process_id,
        "paperless_backlink_updated": result.paperless_backlink_updated,
        "paperless_backlink_error": result.paperless_backlink_error,
        "paperless_backlink_fields": result.paperless_backlink_fields,
        "source_file_trashed": result.trashed,
        "source_file_trash_error": result.trash_error,
        "ocr": {
            "used": result.ocr_used,
            "cache_hit": result.ocr_cache_hit,
            "input_path": str(result.ocr_input_path) if result.ocr_input_path else "",
            "upload_path": str(result.ocr_upload_path) if result.ocr_upload_path else "",
            "output_pdf": str(result.ocr_output_pdf) if result.ocr_output_pdf else "",
            "sidecar_txt": str(result.ocr_sidecar_txt) if result.ocr_sidecar_txt else "",
            "reason": result.ocr_reason,
            "text_before_chars": result.ocr_text_before_chars,
            "text_after_chars": result.ocr_text_after_chars,
            "raw": result.ocr_payload,
        },
        "deck": asdict(result.deck),
        "title": selection.title,
        "created_document_date": selection.created.isoformat() if selection.created else "",
        "tags": [t.name for t in selection.tags] + selection.new_tags,
        "correspondent": selection.correspondent.name if selection.correspondent else "",
        "document_type": selection.document_type.name if selection.document_type else "",
        "storage_path": selection.storage_path.name if selection.storage_path else "",
        "nextcloud": {
            "server": nc.mount.server_url if nc and nc.mount else "",
            "user": nc.mount.user if nc and nc.mount else "",
            "cloud_path": nc.cloud_path if nc else "",
            "web_link": nc.web_link if nc else "",
            "internal_link": nc.internal_link if nc else "",
            "webdav_url": nc.webdav_url if nc else "",
            "file_id": nc.file_id if nc else "",
            "etag": nc.etag if nc else "",
            "journal_path": str(nc.journal_path) if nc and nc.journal_path else "",
            "status": nc.status if nc else "",
        },
        "custom_fields": selection.custom_fields,
    }

    json_path: Path | None = None
    md_path: Path | None = None
    if write_json:
        json_path = base.with_suffix(".json")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_safe_dt), encoding="utf-8")
    if write_markdown:
        md_path = base.with_suffix(".md")
        lines = [
            f"# Paperless-Verknüpfung: {file_info.current_path.name}",
            "",
            f"- Paperless Dokument: {paperless_url or result.document_id or result.task_id}",
            f"- Paperless-Duplikat erkannt: {'ja' if result.duplicate_detected else 'nein'}",
            f"- Vorhandenes Duplikat-Dokument: {result.duplicate_document_id or '—'}",
            f"- Globale Dokument-ID: `{result.global_document_id or '—'}`",
            f"- Vorgangs-ID: `{result.process_id or '—'}`",
            f"- Paperless-Rücklinkfelder aktualisiert: {'ja' if result.paperless_backlink_updated else 'nein'}",
            f"- Task-ID: {result.task_id}",
            f"- Task-Status: {result.task_status or '—'}",
            f"- Task erfolgreich: {'ja' if result.task_success else 'nein'}",
            f"- Task fehlgeschlagen: {'ja' if result.task_failed else 'nein'}",
            f"- Quelldatei im Papierkorb: {'ja' if result.trashed else 'nein'}",
            f"- SHA256: `{file_info.sha256}`",
            f"- OCR verwendet: {'ja' if result.ocr_used else 'nein'}",
            f"- OCR-Grund: {result.ocr_reason or '—'}",
            f"- Deck-Karte: {result.deck.card_url or result.deck.card_id or result.deck.reason or '—'}",
            f"- Deck-Status: {'angelegt' if result.deck.created else ('übersprungen' if result.deck.skipped else ('versucht' if result.deck.attempted else '—'))}",
            f"- Upload-Datei: `{result.ocr_upload_path or file_info.current_path}`",
            f"- Lokaler Pfad: `{file_info.current_path}`",
            f"- Nextcloud Cloud-Pfad: `{payload['nextcloud']['cloud_path']}`",
            f"- Nextcloud Web-Link: {payload['nextcloud']['web_link']}",
            f"- Nextcloud interner Link: {payload['nextcloud']['internal_link']}",
            f"- WebDAV: `{payload['nextcloud']['webdav_url']}`",
            f"- Status: {payload['nextcloud']['status']}",
        ]
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
