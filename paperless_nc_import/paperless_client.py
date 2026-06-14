from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re
import time

import requests

from .config import PaperlessConfig
from .metadata_cache import load_metadata_cache, save_metadata_cache
from .models import CustomField, Entity, Metadata


class PaperlessError(RuntimeError):
    pass


class PaperlessClient:
    def __init__(self, cfg: PaperlessConfig) -> None:
        if not cfg.url:
            raise PaperlessError("Paperless URL fehlt")
        if not cfg.token:
            raise PaperlessError("Paperless Token fehlt")
        self.cfg = cfg
        self.base = cfg.url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {cfg.token}", "Accept": "application/json"})

    def url(self, endpoint: str) -> str:
        endpoint = endpoint.lstrip("/")
        return f"{self.base}/api/{endpoint}"

    def get(self, endpoint: str, **params: Any) -> Any:
        response = self.session.get(self.url(endpoint), params=params, timeout=self.cfg.http_timeout_seconds)
        if response.status_code >= 400:
            raise PaperlessError(f"GET {endpoint} fehlgeschlagen: HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def post_json(self, endpoint: str, payload: dict[str, Any]) -> Any:
        response = self.session.post(self.url(endpoint), json=payload, timeout=self.cfg.http_timeout_seconds)
        if response.status_code >= 400:
            raise PaperlessError(f"POST {endpoint} fehlgeschlagen: HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def patch_json(self, endpoint: str, payload: dict[str, Any]) -> Any:
        response = self.session.patch(self.url(endpoint), json=payload, timeout=self.cfg.http_timeout_seconds)
        if response.status_code >= 400:
            raise PaperlessError(f"PATCH {endpoint} fehlgeschlagen: HTTP {response.status_code}: {response.text[:500]}")
        return response.json() if response.text.strip() else {}

    def list_all(self, endpoint: str, **params: Any) -> list[dict[str, Any]]:
        params.setdefault("page_size", self.cfg.page_size)
        items: list[dict[str, Any]] = []
        next_url: str | None = self.url(endpoint)
        first = True
        while next_url:
            if first:
                response = self.session.get(next_url, params=params, timeout=self.cfg.http_timeout_seconds)
                first = False
            else:
                response = self.session.get(next_url, timeout=self.cfg.http_timeout_seconds)
            if response.status_code >= 400:
                raise PaperlessError(f"GET {endpoint} fehlgeschlagen: HTTP {response.status_code}: {response.text[:500]}")
            data = response.json()
            if isinstance(data, list):
                items.extend(data)
                break
            results = data.get("results")
            if isinstance(results, list):
                items.extend(results)
            next_url = data.get("next")
        return items

    @staticmethod
    def _entity(obj: dict[str, Any]) -> Entity:
        return Entity(
            id=int(obj.get("id", 0)),
            name=str(obj.get("name") or obj.get("title") or ""),
            slug=str(obj.get("slug") or ""),
            color=str(obj.get("color") or ""),
            raw=obj,
        )

    @staticmethod
    def _custom(obj: dict[str, Any]) -> CustomField:
        return CustomField(
            id=int(obj.get("id", 0)),
            name=str(obj.get("name") or ""),
            data_type=str(obj.get("data_type") or obj.get("type") or "string"),
            extra_data=dict(obj.get("extra_data") or {}),
            raw=obj,
        )

    def load_metadata(self, *, use_cache: bool = True) -> Metadata:
        if use_cache:
            cached = load_metadata_cache(self.cfg.metadata_cache_hours)
            if cached:
                return cached

        with ThreadPoolExecutor(max_workers=6) as pool:
            fut_tags = pool.submit(self.list_all, "tags/")
            fut_corr = pool.submit(self.list_all, "correspondents/")
            fut_types = pool.submit(self.list_all, "document_types/")
            fut_paths = pool.submit(self.list_all, "storage_paths/")
            fut_custom = pool.submit(self.list_all, "custom_fields/")

            tags = [self._entity(x) for x in fut_tags.result()]
            correspondents = [self._entity(x) for x in fut_corr.result()]
            document_types = [self._entity(x) for x in fut_types.result()]
            storage_paths = [self._entity(x) for x in fut_paths.result()]
            custom_fields = [self._custom(x) for x in fut_custom.result()]

        metadata = Metadata(
            tags=sorted(tags, key=lambda x: x.name.lower()),
            correspondents=sorted(correspondents, key=lambda x: x.name.lower()),
            document_types=sorted(document_types, key=lambda x: x.name.lower()),
            storage_paths=sorted(storage_paths, key=lambda x: x.name.lower()),
            custom_fields=sorted(custom_fields, key=lambda x: x.name.lower()),
            custom_value_suggestions=self.load_custom_value_suggestions(custom_fields),
            from_cache=False,
        )
        save_metadata_cache(metadata)
        return metadata

    def load_custom_value_suggestions(self, custom_fields: list[CustomField]) -> dict[int, list[str]]:
        if self.cfg.custom_value_suggestion_limit <= 0 or not custom_fields:
            return {}
        ids = {x.id: x for x in custom_fields if x.normalized_type in {"string", "url"}}
        if not ids:
            return {}
        suggestions: dict[int, set[str]] = {field_id: set() for field_id in ids}
        try:
            docs = self.list_all("documents/", page_size=min(self.cfg.custom_value_suggestion_limit, self.cfg.page_size))
        except Exception:
            return {}
        for doc in docs[: self.cfg.custom_value_suggestion_limit]:
            raw = doc.get("custom_fields") or []
            if isinstance(raw, dict):
                iterable = raw.items()
            elif isinstance(raw, list):
                iterable = []
                for item in raw:
                    if isinstance(item, dict):
                        field_id = item.get("field") or item.get("id") or item.get("field_id")
                        value = item.get("value")
                        iterable.append((field_id, value))
            else:
                iterable = []
            for field_id_raw, value in iterable:
                try:
                    field_id = int(field_id_raw)
                except (TypeError, ValueError):
                    continue
                if field_id in suggestions and value not in (None, ""):
                    suggestions[field_id].add(str(value))
        return {field_id: sorted(values, key=str.lower)[:100] for field_id, values in suggestions.items() if values}

    def find_by_name(self, items: list[Entity], name: str) -> Entity | None:
        wanted = name.strip().lower()
        for item in items:
            if item.name.strip().lower() == wanted:
                return item
        return None

    def ensure_tag(self, metadata: Metadata, name: str) -> Entity:
        tag_name = f"{self.cfg.tag_prefix}{name}".strip()
        existing = self.find_by_name(metadata.tags, tag_name)
        if existing:
            return existing
        if not self.cfg.auto_create_tags:
            raise PaperlessError(f"Tag nicht gefunden und auto_create_tags=false: {tag_name}")
        data = self.post_json("tags/", {"name": tag_name})
        tag = self._entity(data)
        metadata.tags.append(tag)
        return tag

    @staticmethod
    def _iso_date_or_datetime(value: datetime | str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def upload_document(
        self,
        file: Path,
        *,
        title: str = "",
        created: datetime | None = None,
        tag_ids: list[int] | None = None,
        correspondent_id: int | None = None,
        document_type_id: int | None = None,
        storage_path_id: int | None = None,
        archive_serial_number: str = "",
        custom_fields: dict[int, Any] | None = None,
    ) -> str:
        fields: list[tuple[str, str]] = []
        if title:
            fields.append(("title", title))
        if created:
            fields.append(("created", self._iso_date_or_datetime(created)))
        if correspondent_id:
            fields.append(("correspondent", str(correspondent_id)))
        if document_type_id:
            fields.append(("document_type", str(document_type_id)))
        if storage_path_id:
            fields.append(("storage_path", str(storage_path_id)))
        if archive_serial_number:
            fields.append(("archive_serial_number", archive_serial_number))
        for tag_id in tag_ids or []:
            fields.append(("tags", str(tag_id)))
        if custom_fields:
            fields.append(("custom_fields", json.dumps({str(k): v for k, v in custom_fields.items()}, ensure_ascii=False)))

        with file.open("rb") as fh:
            files = {"document": (file.name, fh, "application/pdf")}
            response = self.session.post(
                self.url("documents/post_document/"),
                data=fields,
                files=files,
                timeout=self.cfg.http_timeout_seconds,
            )
        if response.status_code >= 400:
            raise PaperlessError(f"Upload fehlgeschlagen: HTTP {response.status_code}: {response.text[:1000]}")
        text = response.text.strip()
        try:
            data = response.json()
        except Exception:
            return text
        if isinstance(data, dict):
            return str(data.get("task_id") or data.get("id") or data.get("task") or text)
        return text.strip('"')

    @staticmethod
    def _extract_document_id_from_task(task: dict[str, Any]) -> int | None:
        for key in (
            "related_document",
            "document",
            "document_id",
            "created_document",
            "created_document_id",
            "result_document",
        ):
            value = task.get(key)
            if isinstance(value, dict):
                value = value.get("id") or value.get("pk")
            try:
                if value not in (None, ""):
                    return int(value)
            except (TypeError, ValueError):
                pass

        # Paperless versions differ in how they expose the import result. Some
        # return only a human-readable result string. Be conservative: require
        # explicit document/id wording before accepting a number.
        for key in ("result", "message", "status_text"):
            text = str(task.get(key) or "")
            m = re.search(r"(?i)(?:document|dokument|document[_ -]?id|id)\D{0,30}(\d+)", text)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass
        return None

    @staticmethod
    def _select_task_from_response(data: Any, task_id: str) -> dict[str, Any]:
        candidates: list[Any] = []
        if isinstance(data, dict):
            for key in ("results", "tasks"):
                value = data.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
            if any(k in data for k in ("status", "state", "result", "related_document", "task_id")):
                candidates.append(data)
        elif isinstance(data, list):
            candidates.extend(data)

        dict_candidates = [x for x in candidates if isinstance(x, dict)]
        if not dict_candidates:
            return {}

        wanted = str(task_id)
        for item in dict_candidates:
            for key in ("task_id", "id", "uuid", "task", "name"):
                if str(item.get(key) or "") == wanted:
                    return item
        return dict_candidates[0]

    @classmethod
    def _extract_document_id_from_any(cls, obj: Any) -> int | None:
        if isinstance(obj, dict):
            direct = cls._extract_document_id_from_task(obj)
            if direct:
                return direct
            for value in obj.values():
                found = cls._extract_document_id_from_any(value)
                if found:
                    return found
        elif isinstance(obj, list):
            for value in obj:
                found = cls._extract_document_id_from_any(value)
                if found:
                    return found
        elif isinstance(obj, str):
            m = re.search(r"(?i)(?:document|dokument|document[_ -]?id|id|pk)\D{0,40}(\d+)", obj)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    return None
        return None

    @staticmethod
    def _status_from_task(task: dict[str, Any]) -> str:
        return str(task.get("status") or task.get("state") or task.get("task_status") or "").upper()

    def wait_task_response(self, task_id: str, *, timeout_seconds: int, interval_seconds: int) -> dict[str, Any]:
        """Wait for a Paperless task and return status/raw response/document id.

        Important safety rule: a Paperless task with status FAILURE/FAILED/REVOKED
        is not a successful import. Numbers found in the raw failure payload must
        not be accepted as document IDs. Otherwise a fallback/error message could
        accidentally cause us to write a misleading Nextcloud link or move the
        source file to trash.
        """
        result: dict[str, Any] = {
            "task_id": task_id,
            "status": "",
            "success": False,
            "failed": False,
            "document_id": None,
            "duplicate": False,
            "duplicate_document_id": None,
            "duplicate_reason": "",
            "raw": {},
        }
        if not task_id:
            return result

        # Existing user configs may still contain 3 seconds from older builds.
        # For this workflow the import result gates Nextcloud sidecars and trash,
        # so poll at least once per second unless the caller chooses sub-second.
        sleep_seconds = max(0.25, min(float(interval_seconds or 1), 1.0))
        deadline = time.time() + timeout_seconds
        success_seen_at: float | None = None
        failure_statuses = {"FAILURE", "FAILED", "REVOKED", "ERROR"}
        success_statuses = {"SUCCESS", "SUCCEEDED", "DONE", "COMPLETED"}

        while time.time() < deadline:
            try:
                data = self.get("tasks/", task_id=task_id)
            except Exception as exc:
                result["status"] = f"poll-error: {exc}"
                time.sleep(sleep_seconds)
                continue

            task = self._select_task_from_response(data, task_id)
            raw = task or data
            result["raw"] = raw

            status = self._status_from_task(task) if task else ""
            if status:
                result["status"] = status

            if status in failure_statuses:
                result["failed"] = True
                result["success"] = False
                # Paperless reports duplicates as failed consumption tasks, but it
                # usually includes related_document.  That is not an import success,
                # but it is a valid Paperless source-of-truth reference.  Keep it
                # separate from document_id so downstream logic can decide whether
                # to create Deck follow-ups and ask the user about deleting the
                # local duplicate.
                duplicate_doc = self._extract_document_id_from_task(task) if task else None
                result_text = str((task or {}).get("result") or (task or {}).get("message") or "")
                if duplicate_doc and "duplicate" in result_text.casefold():
                    result["duplicate"] = True
                    result["duplicate_document_id"] = duplicate_doc
                    result["duplicate_reason"] = result_text
                # Preserve the raw response for sidecar/logging, but do not mark the
                # task as successful and do not set document_id here.
                result["document_id"] = None
                return result

            document_id = self._extract_document_id_from_any(raw)
            if document_id:
                result["document_id"] = document_id
                result["success"] = True
                if not result.get("status"):
                    result["status"] = "SUCCESS"
                return result

            if status in success_statuses:
                result["success"] = True
                # Some Paperless versions report SUCCESS before/without exposing
                # related_document. Poll for a short grace period; afterwards the
                # importer can use a document-search fallback.
                if success_seen_at is None:
                    success_seen_at = time.time()
                elif time.time() - success_seen_at >= 10:
                    return result

            time.sleep(sleep_seconds)
        result["status"] = result.get("status") or "TIMEOUT"
        return result

    @staticmethod
    def _parse_iso_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _doc_id(doc: dict[str, Any]) -> int | None:
        try:
            return int(doc.get("id"))
        except (TypeError, ValueError):
            return None

    def find_document_after_upload(
        self,
        *,
        title: str,
        filename: str,
        created: datetime | None = None,
        uploaded_after: datetime | None = None,
    ) -> int | None:
        """Best-effort fallback when tasks do not expose related_document.

        Only returns an id when the candidate is strong enough. This avoids
        moving the local file to trash based on a weak guess.
        """
        params_list: list[dict[str, Any]] = [
            {"page_size": 25, "ordering": "-added"},
        ]
        if title:
            params_list.append({"page_size": 25, "query": title})
        if filename:
            params_list.append({"page_size": 25, "query": filename})

        docs: dict[int, dict[str, Any]] = {}
        for params in params_list:
            try:
                data = self.get("documents/", **params)
            except Exception:
                continue
            results = data.get("results") if isinstance(data, dict) else data if isinstance(data, list) else []
            if not isinstance(results, list):
                continue
            for doc in results:
                if isinstance(doc, dict):
                    doc_id = self._doc_id(doc)
                    if doc_id:
                        docs[doc_id] = doc

        if not docs:
            return None

        title_norm = title.strip().casefold()
        filename_norm = filename.strip().casefold()
        created_date = created.date().isoformat() if isinstance(created, datetime) else ""
        after_ts = uploaded_after.timestamp() if isinstance(uploaded_after, datetime) else None

        scored: list[tuple[int, int]] = []
        for doc_id, doc in docs.items():
            score = 0
            doc_title = str(doc.get("title") or "").strip().casefold()
            names = " ".join(
                str(doc.get(k) or "")
                for k in ("original_file_name", "archive_filename", "filename", "source_path")
            ).casefold()
            if title_norm and doc_title == title_norm:
                score += 60
            elif title_norm and title_norm in doc_title:
                score += 35
            if filename_norm and filename_norm in names:
                score += 50
            if created_date and str(doc.get("created") or "").startswith(created_date):
                score += 10
            if after_ts is not None:
                added = self._parse_iso_datetime(doc.get("added") or doc.get("created_at") or doc.get("modified"))
                if added and added.timestamp() >= after_ts - 300:
                    score += 25
            if score >= 60:
                scored.append((score, doc_id))

        if not scored:
            return None
        scored.sort(reverse=True)
        # If the top result is not clearly better, avoid a dangerous false match.
        if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][0] < 100:
            return None
        return scored[0][1]


    def get_document(self, document_id: int) -> dict[str, Any]:
        data = self.get(f"documents/{int(document_id)}/")
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _custom_fields_to_dict(raw: Any) -> dict[str, Any]:
        """Normalize Paperless custom_fields response to {field_id: value}.

        Paperless versions/API shapes differ: some expose a mapping, others a
        list with field/id/value keys. Keep unknown values out and do not crash.
        """
        out: dict[str, Any] = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key not in (None, ""):
                    out[str(key)] = value
            return out
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                field_id = item.get("field") or item.get("field_id") or item.get("id")
                value = item.get("value")
                if field_id not in (None, ""):
                    out[str(field_id)] = value
        return out

    def update_document_custom_fields(self, document_id: int, values: dict[int, Any]) -> dict[str, Any]:
        """Merge and write configured cross-reference custom fields.

        The merge is intentional: the importer must not wipe user-maintained
        Paperless custom fields when it writes Deck/global identifiers.
        """
        clean = {str(int(k)): v for k, v in values.items() if k and v not in (None, "")}
        if not clean:
            return {}
        document = self.get_document(document_id)
        merged = self._custom_fields_to_dict(document.get("custom_fields"))
        merged.update(clean)
        return self.patch_json(f"documents/{int(document_id)}/", {"custom_fields": merged})

    def wait_task(self, task_id: str, *, timeout_seconds: int, interval_seconds: int) -> int | None:
        return self.wait_task_response(
            task_id, timeout_seconds=timeout_seconds, interval_seconds=interval_seconds
        ).get("document_id")

    def document_url(self, document_id: int | None) -> str:
        if not document_id:
            return ""
        return self.cfg.document_url_template.format(base=self.base, id=document_id)
