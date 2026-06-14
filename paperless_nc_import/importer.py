from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
import shutil

from .config import AppConfig
from .deck_client import maybe_create_followup_card
from .fs_utils import birth_prefixed_path, birthtime, sha256_file, title_from_filename
from .models import FileInfo, ImportResult, ImportSelection, Metadata, NextcloudMount
from .nextcloud_links import build_nextcloud_reference
from .ocr import OcrError, OcrProcessor
from .paperless_client import PaperlessClient
from .sidecar import write_sidecars
from .state import StateStore
from .trash import move_to_trash


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"raw": value}


def _host_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.netloc or parsed.path or "").strip().lower()
    except Exception:
        return ""


def _safe_format(template: str, values: dict[str, Any], fallback: str = "") -> str:
    try:
        return template.format(**values)
    except Exception:
        return fallback

class Importer:
    def __init__(self, cfg: AppConfig, client: PaperlessClient | None = None) -> None:
        self.cfg = cfg
        self.client = client
        self.state = StateStore(cfg.import_.state_file)

    def build_file_info(self, path: Path, mounts: list[NextcloudMount] | None = None) -> FileInfo:
        path = path.resolve()
        bt = birthtime(path)
        created = bt if self.cfg.import_.set_created_from_birthdate else datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        info = FileInfo(
            original_path=path,
            current_path=path,
            sha256=sha256_file(path),
            birthtime=bt,
            created=created,
            title=title_from_filename(path),
        )
        if mounts is not None:
            info.nextcloud = build_nextcloud_reference(path, mounts)
        return info

    def default_selection(self, file_info: FileInfo, metadata: Metadata | None = None) -> ImportSelection:
        sel = ImportSelection(title=file_info.title, created=file_info.created)
        if metadata:
            default = self.cfg.import_.default_tag.strip()
            if default:
                for tag in metadata.tags:
                    if tag.name.casefold() == default.casefold():
                        sel.tags.append(tag)
                        break
            # Do not preselect origin/parent-folder/Nextcloud tags.
            # The import mask should not silently turn provenance into classification.
            # Only the configured default tag (usually "Posteingang") is selected.
        return sel

    def _rename_if_needed(self, info: FileInfo, dry_run: bool) -> Path | None:
        if not self.cfg.import_.rename_with_birthdate:
            return None
        target = birth_prefixed_path(info.current_path, info.birthtime, self.cfg.import_.date_format)
        if target == info.current_path:
            return None
        if dry_run:
            return target
        info.current_path.rename(target)
        info.current_path = target
        return target

    def _assign_global_ids(self, result: ImportResult) -> None:
        if not result.document_id:
            return
        host = _host_from_url(self.cfg.paperless.url)
        values = {
            "paperless_host": host,
            "paperless_base": self.cfg.paperless.url.rstrip("/"),
            "paperless_document_id": result.document_id,
            "paperless_url": result.paperless_url,
        }
        default_global = f"urn:paperless:{host}:document:{result.document_id}" if host else f"urn:paperless:document:{result.document_id}"
        result.global_document_id = _safe_format(
            self.cfg.custom.global_document_id_template, values, default_global
        ) or default_global
        values["global_document_id"] = result.global_document_id
        result.process_id = _safe_format(
            self.cfg.custom.process_id_template, values, result.global_document_id
        ) or result.global_document_id

    def _paperless_backlink_values(self, result: ImportResult) -> dict[int, Any]:
        cfg = self.cfg.custom
        values: dict[int, Any] = {}
        if cfg.field_global_document_id_id and result.global_document_id:
            values[cfg.field_global_document_id_id] = result.global_document_id
        if cfg.field_process_id_id and result.process_id:
            values[cfg.field_process_id_id] = result.process_id
        if cfg.field_deck_card_url_id and result.deck.card_url:
            values[cfg.field_deck_card_url_id] = result.deck.card_url
        if cfg.field_deck_card_id_id and result.deck.card_id:
            values[cfg.field_deck_card_id_id] = str(result.deck.card_id)
        return values

    def _update_paperless_cross_references(self, result: ImportResult) -> None:
        if not self.client or not result.document_id:
            return
        if result.task_failed and not result.duplicate_detected:
            return
        values = self._paperless_backlink_values(result)
        result.paperless_backlink_fields = dict(values)
        if not values:
            return
        try:
            self.client.update_document_custom_fields(result.document_id, values)
            result.paperless_backlink_updated = True
            result.warnings.append("Paperless-Custom-Fields für Rückverweise/Vorgangs-ID aktualisiert.")
        except Exception as exc:
            result.paperless_backlink_error = str(exc)
            result.warnings.append(f"Paperless-Rücklink-Custom-Fields konnten nicht aktualisiert werden: {exc}")

    def import_one(
        self,
        file_info: FileInfo,
        selection: ImportSelection,
        metadata: Metadata,
        *,
        dry_run: bool = False,
        progress: Callable[[str, int], None] | None = None,
    ) -> ImportResult:
        result = ImportResult(file=file_info.current_path, dry_run=dry_run)
        if self.cfg.import_.prevent_duplicates and self.state.contains(file_info.sha256):
            # Local state is advisory only.  In multi-client setups Paperless is
            # the source of truth for duplicate handling; a local hash must never
            # block tests or valid imports from another workstation.
            result.warnings.append(
                "Datei-Hash ist im lokalen Client-State bekannt; Import wird trotzdem versucht. "
                "Paperless ist die maßgebliche Duplikat-Quelle."
            )

        renamed = self._rename_if_needed(file_info, dry_run)
        result.renamed_to = renamed
        # Keep result.file as the current source path after an optional birthdate
        # rename so later GUI decisions such as duplicate trashing affect the
        # correct file.
        result.file = file_info.current_path

        ocr_upload_path = file_info.current_path
        try:
            ocr_result = OcrProcessor(self.cfg.ocr).prepare(
                file_info.current_path,
                sha256=file_info.sha256,
                progress=progress,
            )
            result.ocr_used = ocr_result.used_ocr
            result.ocr_cache_hit = ocr_result.cache_hit
            result.ocr_input_path = ocr_result.input_path
            result.ocr_upload_path = ocr_result.upload_path
            result.ocr_output_pdf = ocr_result.output_pdf
            result.ocr_sidecar_txt = ocr_result.sidecar_txt
            result.ocr_reason = ocr_result.reason
            result.ocr_text_before_chars = ocr_result.text_before_chars
            result.ocr_text_after_chars = ocr_result.text_after_chars
            result.ocr_payload = ocr_result.to_payload()
            ocr_upload_path = ocr_result.upload_path
            if ocr_result.used_ocr:
                result.warnings.append(
                    f"OCR verwendet: {ocr_result.reason}; Textzeichen vorher/nachher: "
                    f"{ocr_result.text_before_chars}/{ocr_result.text_after_chars}"
                )
        except OcrError as exc:
            if self.cfg.ocr.fail_on_error:
                raise
            result.warnings.append(f"OCR fehlgeschlagen, Original wird verwendet: {exc}")

        if dry_run:
            result.task_id = "dry-run"
            return result

        if not self.client:
            raise RuntimeError("PaperlessClient fehlt")

        tags = list(selection.tags)
        for name in selection.new_tags:
            if name.strip():
                tags.append(self.client.ensure_tag(metadata, name.strip()))

        upload_started_at = datetime.now(timezone.utc)
        task_id = self.client.upload_document(
            ocr_upload_path,
            title=selection.title,
            created=selection.created,
            tag_ids=[t.id for t in tags],
            correspondent_id=selection.correspondent.id if selection.correspondent else None,
            document_type_id=selection.document_type.id if selection.document_type else None,
            storage_path_id=selection.storage_path.id if selection.storage_path else None,
            archive_serial_number=selection.asn,
            custom_fields=selection.custom_fields,
        )
        result.task_id = task_id
        result.uploaded = True

        if self.cfg.import_.wait_for_task:
            task_response = self.client.wait_task_response(
                task_id,
                timeout_seconds=self.cfg.import_.task_wait_timeout_seconds,
                interval_seconds=self.cfg.import_.task_wait_interval_seconds,
            )
            result.task_status = str(task_response.get("status") or "")
            result.task_success = bool(task_response.get("success"))
            result.task_failed = bool(task_response.get("failed"))
            result.task_response = _json_object(task_response.get("raw"))
            result.duplicate_detected = bool(task_response.get("duplicate"))
            if task_response.get("duplicate_document_id"):
                try:
                    result.duplicate_document_id = int(task_response.get("duplicate_document_id"))
                except Exception:
                    result.duplicate_document_id = None
            result.duplicate_reason = str(task_response.get("duplicate_reason") or "")

            failure_statuses = {"FAILURE", "FAILED", "REVOKED", "ERROR"}
            success_statuses = {"SUCCESS", "SUCCEEDED", "DONE", "COMPLETED"}
            status_upper = result.task_status.upper()
            if status_upper in failure_statuses:
                result.task_failed = True
                result.task_success = False

            doc_id = task_response.get("document_id")
            if doc_id and not result.task_failed:
                result.document_id = int(doc_id)

            if (
                not result.document_id
                and not result.task_failed
                and (result.task_success or status_upper in success_statuses)
            ):
                fallback_id = self.client.find_document_after_upload(
                    title=selection.title,
                    filename=ocr_upload_path.name,
                    created=selection.created,
                    uploaded_after=upload_started_at,
                )
                if fallback_id:
                    result.document_id = fallback_id
                    result.task_success = True
                    result.warnings.append(
                        "Paperless-Dokument-ID wurde per Dokumentensuche nach erfolgreicher Task-Rückmeldung gefunden."
                    )

            if result.duplicate_detected and result.duplicate_document_id:
                # Duplicate is a valid Paperless source-of-truth reference, but not
                # a successful import.  Use it for cross-system workflow steps and
                # show the existing document to the user before deciding about the
                # local source file.
                result.document_id = result.duplicate_document_id
                result.paperless_url = self.client.document_url(result.document_id)
                self._assign_global_ids(result)
                try:
                    result.existing_document = self.client.get_document(result.document_id)
                except Exception as exc:
                    result.warnings.append(f"Vorhandenes Paperless-Dokument #{result.document_id} konnte nicht gelesen werden: {exc}")
                result.warnings.append(
                    f"Paperless meldet Duplikat; vorhandenes Dokument #{result.document_id} wird als Quelle der Wahrheit verwendet."
                )
            elif result.document_id and not result.task_failed:
                result.paperless_url = self.client.document_url(result.document_id)
                self._assign_global_ids(result)
            elif result.task_failed:
                result.warnings.append(
                    "Paperless meldet FAILURE/FAILED ohne verwertbare Duplikat-Referenz; Dokument-ID und Papierkorb-Schritt werden nicht akzeptiert."
                )
            else:
                result.warnings.append(
                    "Paperless hat noch keine sichere Dokument-ID zurückgegeben; Rückverweis enthält nur Task-ID, Quelldatei bleibt erhalten."
                )
        else:
            result.warnings.append(
                "wait_for_task=false: es liegt nur die Task-ID vor; Rückverweis/Trash werden nicht finalisiert."
            )

        document_resolved = bool(result.document_id) and ((result.task_success and not result.task_failed) or result.duplicate_detected)

        deck_needed = False
        if not dry_run and document_resolved:
            try:
                deck_result = maybe_create_followup_card(
                    cfg=self.cfg,
                    file_info=file_info,
                    selection=selection,
                    metadata=metadata,
                    result=result,
                )
                # Copy compatible dataclass fields without importing GUI-facing types here.
                for key, value in deck_result.to_payload().items():
                    if hasattr(result.deck, key):
                        setattr(result.deck, key, value)
                deck_needed = bool(result.deck.attempted)
                if result.deck.created:
                    result.warnings.append(f"Nextcloud Deck-Karte angelegt: {result.deck.card_url or result.deck.card_id}")
                elif result.deck.reason and not result.deck.skipped:
                    result.warnings.append("Deck-Karte wurde nicht angelegt: " + result.deck.reason)
            except Exception as exc:
                deck_needed = True
                result.deck.attempted = True
                result.deck.created = False
                result.deck.reason = str(exc)
                result.warnings.append(f"Deck-Karte konnte nicht angelegt werden: {exc}")

        if not dry_run and document_resolved:
            self._update_paperless_cross_references(result)

        if self.cfg.import_.trash_after_success:
            deck_blocks_trash = (
                self.cfg.deck.enabled
                and self.cfg.deck.require_deck_success_for_trash
                and deck_needed
                and not result.deck.created
            )
            backlink_blocks_trash = (
                self.cfg.custom.require_backlink_update_for_trash
                and bool(result.paperless_backlink_fields)
                and not result.paperless_backlink_updated
            )
            if deck_blocks_trash:
                result.warnings.append(
                    "Quelldatei wurde nicht verschoben, weil eine Wiedervorlage gesetzt ist, aber keine Deck-Karte sicher angelegt wurde."
                )
            elif backlink_blocks_trash:
                result.warnings.append(
                    "Quelldatei wurde nicht verschoben, weil konfigurierte Paperless-Rücklink-Custom-Fields nicht sicher aktualisiert wurden."
                )
            elif result.duplicate_detected:
                result.warnings.append(
                    "Paperless hat ein vorhandenes Dokument referenziert. Die lokale Datei wird nicht automatisch gelöscht; bitte im Duplikat-Dialog entscheiden."
                )
            elif result.document_id and result.task_success and not result.task_failed:
                try:
                    move_to_trash(file_info.current_path)
                    result.trashed = True
                except Exception as exc:
                    result.trash_error = str(exc)
                    result.warnings.append(f"Quelldatei konnte nicht in den Papierkorb verschoben werden: {exc}")
            elif not dry_run:
                result.warnings.append(
                    "Quelldatei wurde nicht verschoben, weil keine erfolgreiche Paperless-Task mit sicherer Dokument-ID vorliegt."
                )

        if self.cfg.nextcloud.write_sidecar:
            result.sidecar_json, result.sidecar_md = write_sidecars(
                link_dir_name=self.cfg.nextcloud.link_dir_name,
                file_info=file_info,
                selection=selection,
                result=result,
                paperless_url=result.paperless_url,
                write_json=self.cfg.nextcloud.write_json,
                write_markdown=self.cfg.nextcloud.write_markdown,
            )
        if result.document_id and ((result.task_success and not result.task_failed) or result.duplicate_detected):
            self.state.add(
                sha256=file_info.sha256,
                file=file_info.current_path,
                task_id=result.task_id,
                document_id=result.document_id,
            )
        return result
