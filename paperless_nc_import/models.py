from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

CustomType = Literal[
    "string",
    "url",
    "date",
    "boolean",
    "integer",
    "float",
    "monetary",
    "select",
]


@dataclass(slots=True)
class Entity:
    id: int
    name: str
    slug: str = ""
    color: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        if self.color:
            return f"{self.name} [#{self.id}]"
        return f"{self.name} [#{self.id}]"


@dataclass(slots=True)
class CustomField:
    id: int
    name: str
    data_type: str = "string"
    extra_data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_type(self) -> CustomType:
        value = (self.data_type or "string").lower().strip()
        aliases = {
            "str": "string",
            "text": "string",
            "int": "integer",
            "bool": "boolean",
            "monetary": "monetary",
            "currency": "monetary",
            "link": "url",
        }
        value = aliases.get(value, value)
        if value in {"string", "url", "date", "boolean", "integer", "float", "monetary", "select"}:
            return value  # type: ignore[return-value]
        return "string"

    def label(self) -> str:
        return f"{self.name} [#{self.id}, {self.normalized_type}]"


@dataclass(slots=True)
class Metadata:
    tags: list[Entity] = field(default_factory=list)
    correspondents: list[Entity] = field(default_factory=list)
    document_types: list[Entity] = field(default_factory=list)
    storage_paths: list[Entity] = field(default_factory=list)
    custom_fields: list[CustomField] = field(default_factory=list)
    custom_value_suggestions: dict[int, list[str]] = field(default_factory=dict)
    from_cache: bool = False


@dataclass(slots=True)
class NextcloudMount:
    local_root: Path
    server_url: str
    user: str = ""
    remote_root: str = "/"
    journal_path: Path | None = None
    account_name: str = ""

    def contains(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.local_root.resolve())
            return True
        except ValueError:
            return False


@dataclass(slots=True)
class NextcloudReference:
    mount: NextcloudMount | None
    local_path: Path
    cloud_path: str = ""
    web_link: str = ""
    internal_link: str = ""
    webdav_url: str = ""
    file_id: str = ""
    oc_id: str = ""
    etag: str = ""
    journal_path: Path | None = None
    status: str = ""


@dataclass(slots=True)
class FileInfo:
    original_path: Path
    current_path: Path
    sha256: str
    birthtime: datetime
    created: datetime
    title: str
    nextcloud: NextcloudReference | None = None


@dataclass(slots=True)
class ImportSelection:
    tags: list[Entity] = field(default_factory=list)
    new_tags: list[str] = field(default_factory=list)
    correspondent: Entity | None = None
    document_type: Entity | None = None
    storage_path: Entity | None = None
    title: str = ""
    created: datetime | None = None
    asn: str = ""
    custom_fields: dict[int, Any] = field(default_factory=dict)
    # Deck target selected in the GUI.  These are deliberately per-import
    # values because multiple Nextcloud instances / boards can exist and
    # hard-coded board_id/stack_id values are too brittle.
    deck_board_id: int | None = None
    deck_stack_id: int | None = None
    # Compact lead time / effort estimate before the due date, e.g. 5d or 3h.
    deck_effort: str = ""


@dataclass(slots=True)
class DeckResult:
    attempted: bool = False
    created: bool = False
    skipped: bool = False
    reason: str = ""
    server_url: str = ""
    username: str = ""
    board_id: int | None = None
    stack_id: int | None = None
    card_id: int | None = None
    card_url: str = ""
    label_id: int | None = None
    label_title: str = ""
    due_date: str = ""
    start_date: str = ""
    effort: str = ""
    title: str = ""
    route_name: str = ""
    marker: str = ""
    response: dict[str, Any] | list[Any] | str | None = None


@dataclass(slots=True)
class ImportResult:
    file: Path
    dry_run: bool
    task_id: str = ""
    document_id: int | None = None
    paperless_url: str = ""
    task_status: str = ""
    task_success: bool = False
    task_failed: bool = False
    task_response: dict[str, Any] = field(default_factory=dict)
    renamed_to: Path | None = None
    uploaded: bool = False
    sidecar_json: Path | None = None
    sidecar_md: Path | None = None
    trashed: bool = False
    trash_error: str = ""
    ocr_used: bool = False
    ocr_cache_hit: bool = False
    ocr_input_path: Path | None = None
    ocr_upload_path: Path | None = None
    ocr_output_pdf: Path | None = None
    ocr_sidecar_txt: Path | None = None
    ocr_reason: str = ""
    ocr_text_before_chars: int = 0
    ocr_text_after_chars: int = 0
    ocr_payload: dict[str, Any] = field(default_factory=dict)
    deck: DeckResult = field(default_factory=DeckResult)
    global_document_id: str = ""
    process_id: str = ""
    paperless_backlink_updated: bool = False
    paperless_backlink_error: str = ""
    paperless_backlink_fields: dict[int, Any] = field(default_factory=dict)
    duplicate_detected: bool = False
    duplicate_document_id: int | None = None
    duplicate_reason: str = ""
    existing_document: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
