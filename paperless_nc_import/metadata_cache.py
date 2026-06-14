from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from .config import xdg_cache_home, APP_NAME
from .models import CustomField, Entity, Metadata


def cache_path() -> Path:
    return xdg_cache_home() / APP_NAME / "metadata-cache.json"


def _entity_from(data: dict) -> Entity:
    return Entity(
        id=int(data.get("id", 0)),
        name=str(data.get("name", "")),
        slug=str(data.get("slug", "")),
        color=str(data.get("color", "")),
        raw=dict(data.get("raw", {}) or {}),
    )


def _custom_from(data: dict) -> CustomField:
    return CustomField(
        id=int(data.get("id", 0)),
        name=str(data.get("name", "")),
        data_type=str(data.get("data_type", "string")),
        extra_data=dict(data.get("extra_data", {}) or {}),
        raw=dict(data.get("raw", {}) or {}),
    )


def load_metadata_cache(max_age_hours: int) -> Metadata | None:
    path = cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        created = datetime.fromisoformat(payload.get("created", ""))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created > timedelta(hours=max_age_hours):
            return None
        data = payload.get("metadata", {}) or {}
        return Metadata(
            tags=[_entity_from(x) for x in data.get("tags", [])],
            correspondents=[_entity_from(x) for x in data.get("correspondents", [])],
            document_types=[_entity_from(x) for x in data.get("document_types", [])],
            storage_paths=[_entity_from(x) for x in data.get("storage_paths", [])],
            custom_fields=[_custom_from(x) for x in data.get("custom_fields", [])],
            custom_value_suggestions={int(k): list(v) for k, v in (data.get("custom_value_suggestions", {}) or {}).items()},
            from_cache=True,
        )
    except Exception:
        return None


def save_metadata_cache(metadata: Metadata) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "tags": [asdict(x) for x in metadata.tags],
            "correspondents": [asdict(x) for x in metadata.correspondents],
            "document_types": [asdict(x) for x in metadata.document_types],
            "storage_paths": [asdict(x) for x in metadata.storage_paths],
            "custom_fields": [asdict(x) for x in metadata.custom_fields],
            "custom_value_suggestions": metadata.custom_value_suggestions,
        },
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
