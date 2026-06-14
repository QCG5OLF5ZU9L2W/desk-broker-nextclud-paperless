from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import sys

import yaml

from .extraction import CustomFieldExtractionRule

APP_NAME = "paperless-nc-import"


def xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def xdg_state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))


def default_config_path() -> Path:
    return xdg_config_home() / APP_NAME / "config.yaml"


def expand_path(value: str | Path | None) -> Path:
    if not value:
        return Path("")
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


def _load_env_file(path: Path) -> None:
    """Load a small KEY=value secrets file into os.environ if not set already.

    This is intentionally tiny and shell-compatible enough for app passwords:
    blank lines and # comments are ignored; optional `export KEY=value` is
    accepted; single/double quotes around values are stripped. Existing
    environment variables win over file values.
    """
    if not path or not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        os.environ[key] = value


def default_nextcloud_config_path() -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "Nextcloud" / "nextcloud.cfg"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "Nextcloud" / "nextcloud.cfg"
    return xdg_config_home() / "Nextcloud" / "nextcloud.cfg"


@dataclass(slots=True)
class PaperlessConfig:
    url: str = ""
    token: str = ""
    tag_prefix: str = ""
    auto_create_tags: bool = True
    auto_create_correspondents: bool = False
    auto_create_document_types: bool = False
    auto_create_storage_paths: bool = False
    document_url_template: str = "{base}/documents/{id}"
    http_timeout_seconds: int = 60
    page_size: int = 500
    metadata_cache_hours: int = 1
    custom_value_suggestion_limit: int = 250


@dataclass(slots=True)
class NextcloudConfig:
    auto_detect: bool = True
    config_path: Path = field(default_factory=default_nextcloud_config_path)
    write_sidecar: bool = True
    write_json: bool = True
    write_markdown: bool = True
    link_dir_name: str = "paperless-links"
    write_comment: bool = False
    server_url: str = ""
    user: str = ""
    app_password: str = ""


@dataclass(slots=True)
class DeckRouteConfig:
    # Matching is done against the Nextcloud mount resolved from the selected file path.
    # This avoids a single hard-coded Nextcloud instance.
    name: str = ""
    match_server: str = ""
    match_user: str = ""
    match_local_root: str = ""
    match_remote_root: str = ""
    username: str = ""
    app_password: str = ""
    app_password_env: str = ""
    board_id: int = 0
    stack_id: int = 0


@dataclass(slots=True)
class DeckConfig:
    enabled: bool = False
    # Optional shell-style env file for Deck app-passwords. This is used by
    # Nautilus as well as CLI and avoids putting secrets directly into YAML.
    secrets_file: Path = field(default_factory=lambda: xdg_config_home() / APP_NAME / "secrets.env")
    # IDs are preferred; names are a convenience fallback.
    followup_field_ids: list[int] = field(default_factory=list)
    followup_field_names: list[str] = field(default_factory=lambda: ["Wiedervorlage"])
    create_only_after_paperless_success: bool = True
    require_document_id: bool = True
    require_deck_success_for_trash: bool = True
    todo_label: str = "Todo"
    todo_label_color: str = "31CC7C"
    auto_create_label: bool = True
    title_template: str = "Wiedervorlage: {document_title}"
    description_template: str = "{paperless_url}\n\n--- Erste Seite ---\n{first_page_text}"
    max_first_page_chars: int = 4000
    due_time: str = "09:00"
    timezone: str = "Europe/Berlin"
    # Default lead time / estimated processing effort before the due date.
    # Examples: 5d = 5 Arbeitstage, 3h = 3 Stunden, 30m = 30 Minuten, 10kt = 10 Kalendertage.
    default_effort: str = ""
    effort_holiday_state: str = "BE"
    http_timeout_seconds: int = 30
    routes: list[DeckRouteConfig] = field(default_factory=list)


@dataclass(slots=True)
class ImportConfig:
    inbox_dir: Path = Path("~/Documents/nc.5st.eu/paperless_ausgang")
    pattern: str = "img*.pdf"
    min_age_seconds: int = 60
    rename_with_birthdate: bool = True
    date_format: str = "%Y-%m-%d_%H-%M-%S"
    set_created_from_birthdate: bool = True
    set_title_from_filename: bool = True
    default_tag: str = "Posteingang"
    default_tag_from_parent_folder: bool = False
    prevent_duplicates: bool = False
    state_file: Path = field(default_factory=lambda: xdg_state_home() / APP_NAME / "uploaded.jsonl")
    wait_for_task: bool = True
    trash_after_success: bool = True
    task_wait_timeout_seconds: int = 240
    task_wait_interval_seconds: int = 1


@dataclass(slots=True)
class GuiConfig:
    enabled: bool = True
    auto_for_explicit_files: bool = True
    preload_paperless_metadata: bool = True
    confirm_before_upload: bool = True
    viewer_mode: str = "internal"  # internal | external | off
    split_ratio: list[int] = field(default_factory=lambda: [50, 50])
    close_after_success: bool = True
    close_after_seconds: int = 2


@dataclass(slots=True)
class OcrConfig:
    enabled: bool = True
    # auto: OCR only when no text layer is found; never: do nothing;
    # redo/force: re-OCR even when a text layer exists.
    mode: str = "auto"  # auto | never | redo | force
    archive_engine: str = "ocrmypdf"
    assist_engine: str = "none"  # none | paddleocr (reserved for v0.7 assist extraction)
    languages: list[str] = field(default_factory=lambda: ["deu", "eng"])
    cache_dir: Path = field(default_factory=lambda: xdg_cache_home() / APP_NAME / "ocr")
    upload: str = "ocr_pdf"  # ocr_pdf | original
    jobs: int = 0
    output_type: str = "pdfa"
    rotate_pages: bool = True
    deskew: bool = True
    clean: bool = True
    sidecar_text: bool = True
    min_text_chars: int = 40
    text_probe_pages: int = 3
    timeout_seconds: int = 0
    fail_on_error: bool = True


@dataclass(slots=True)
class CustomConfig:
    # Optional stable default mappings. GUI can override them per import.
    field_nextcloud_web_url_id: int | None = None
    field_nextcloud_cloud_path_id: int | None = None
    field_nextcloud_webdav_url_id: int | None = None
    field_nextcloud_fileid_id: int | None = None
    field_nextcloud_etag_id: int | None = None
    field_local_path_id: int | None = None
    field_sha256_id: int | None = None
    field_original_path_id: int | None = None
    field_birthtime_id: int | None = None

    # Cross-system references written back to Paperless after a document id and
    # optionally a Deck card are known. These make Paperless and Deck reference
    # each other instead of relying only on local sidecar files.
    field_deck_card_url_id: int | None = None
    field_deck_card_id_id: int | None = None
    field_global_document_id_id: int | None = None
    field_process_id_id: int | None = None
    global_document_id_template: str = "urn:paperless:{paperless_host}:document:{paperless_document_id}"
    process_id_template: str = "{global_document_id}"
    require_backlink_update_for_trash: bool = False

    # OCR/text based GUI prefill rules for existing Paperless custom fields.
    # field_id is preferred; field_name is a readable fallback for shared configs.
    custom_field_extraction_rules: list[CustomFieldExtractionRule] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    paperless: PaperlessConfig = field(default_factory=PaperlessConfig)
    nextcloud: NextcloudConfig = field(default_factory=NextcloudConfig)
    deck: DeckConfig = field(default_factory=DeckConfig)
    import_: ImportConfig = field(default_factory=ImportConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    custom: CustomConfig = field(default_factory=CustomConfig)
    path: Path = field(default_factory=default_config_path)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ja", "on"}
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_present(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return default


def _as_optional_str_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    return [str(value)]


def _as_group(value: Any) -> int | str:
    if value in (None, ""):
        return 1
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _as_custom_field_extraction_rules(value: Any) -> list[CustomFieldExtractionRule]:
    if value in (None, ""):
        return []

    raw_items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        # Convenience form:
        # custom_field_extraction_rules:
        #   "3": {field_name: Rechnungsbetrag, extractor: receipt_total}
        for field_id, item in value.items():
            if not isinstance(item, dict):
                continue
            merged = dict(item)
            merged.setdefault("field_id", field_id)
            raw_items.append(merged)
    elif isinstance(value, list):
        raw_items = [dict(item) for item in value if isinstance(item, dict)]

    rules: list[CustomFieldExtractionRule] = []
    for item in raw_items:
        patterns = _as_optional_str_list(
            _first_present(item, "patterns", "regexes", "regex", "pattern")
        )
        flags = _as_optional_str_list(item.get("flags")) or ["ignorecase", "multiline"]
        rules.append(
            CustomFieldExtractionRule(
                field_id=_optional_int(_first_present(item, "field_id", "id", "custom_field_id")),
                field_name=str(_first_present(item, "field_name", "name", default="") or ""),
                field_type=str(_first_present(item, "field_type", "data_type", "type", default="") or ""),
                source=str(item.get("source", "ocr_text") or "ocr_text"),
                extractor=str(item.get("extractor", "regex") or "regex"),
                patterns=patterns,
                group=_as_group(item.get("group", 1)),
                normalize=str(item.get("normalize", "") or ""),
                flags=flags,
                priority=_as_int(item.get("priority"), 100),
                enabled=_as_bool(item.get("enabled"), True),
                label=str(item.get("label", "") or ""),
            )
        )
    return rules


def _as_int_list(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        raw = [x.strip() for x in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _as_deck_routes(value: Any) -> list[DeckRouteConfig]:
    if not isinstance(value, list):
        return []
    routes: list[DeckRouteConfig] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        routes.append(
            DeckRouteConfig(
                name=str(item.get("name", "")),
                match_server=str(item.get("match_server", "")).rstrip("/"),
                match_user=str(item.get("match_user", "")),
                match_local_root=str(item.get("match_local_root", "")),
                match_remote_root=str(item.get("match_remote_root", "")),
                username=str(item.get("username", "")),
                app_password=str(item.get("app_password", "")),
                app_password_env=str(item.get("app_password_env", "")),
                # board_id/stack_id are optional defaults only; the GUI can and should
                # select the real Deck target from the API per import.
                board_id=_as_int(item.get("board_id", item.get("default_board_id")), 0),
                stack_id=_as_int(item.get("stack_id", item.get("default_stack_id")), 0),
            )
        )
    return routes

def _as_str_list(value: Any, default: list[str]) -> list[str]:
    if value is None or value == "":
        return list(default)
    if isinstance(value, str):
        parts = [x.strip() for x in value.replace("+", ",").split(",")]
        return [x for x in parts if x] or list(default)
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()] or list(default)
    return list(default)

def load_config(path: Path | None = None) -> AppConfig:
    config_path = expand_path(path) if path else default_config_path()
    data: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Konfiguration {config_path} enthält kein YAML-Objekt")
            data = loaded

    p = data.get("paperless", {}) or {}
    nc = data.get("nextcloud", {}) or {}
    deck = data.get("deck", {}) or {}
    imp = data.get("import", {}) or {}
    gui = data.get("gui", {}) or {}
    ocr = data.get("ocr", {}) or {}
    custom = data.get("custom", {}) or {}

    cfg = AppConfig(path=config_path)
    cfg.paperless = PaperlessConfig(
        url=str(p.get("url", "")).rstrip("/"),
        token=str(p.get("token", "")),
        tag_prefix=str(p.get("tag_prefix", "")),
        auto_create_tags=_as_bool(p.get("auto_create_tags"), True),
        auto_create_correspondents=_as_bool(p.get("auto_create_correspondents"), False),
        auto_create_document_types=_as_bool(p.get("auto_create_document_types"), False),
        auto_create_storage_paths=_as_bool(p.get("auto_create_storage_paths"), False),
        document_url_template=str(p.get("document_url_template", "{base}/documents/{id}")),
        http_timeout_seconds=_as_int(p.get("http_timeout_seconds"), 60),
        page_size=_as_int(p.get("page_size"), 500),
        metadata_cache_hours=_as_int(p.get("metadata_cache_hours"), 1),
        custom_value_suggestion_limit=_as_int(p.get("custom_value_suggestion_limit"), 250),
    )
    cfg.nextcloud = NextcloudConfig(
        auto_detect=_as_bool(nc.get("auto_detect"), True),
        config_path=expand_path(nc.get("config_path") or default_nextcloud_config_path()),
        write_sidecar=_as_bool(nc.get("write_sidecar"), True),
        write_json=_as_bool(nc.get("write_json"), True),
        write_markdown=_as_bool(nc.get("write_markdown"), True),
        link_dir_name=str(nc.get("link_dir_name", "paperless-links")),
        write_comment=_as_bool(nc.get("write_comment"), False),
        server_url=str(nc.get("server_url", "")).rstrip("/"),
        user=str(nc.get("user", "")),
        app_password=str(nc.get("app_password", "")),
    )
    cfg.deck = DeckConfig(
        enabled=_as_bool(deck.get("enabled"), False),
        secrets_file=expand_path(deck.get("secrets_file") or (xdg_config_home() / APP_NAME / "secrets.env")),
        followup_field_ids=_as_int_list(deck.get("followup_field_ids")),
        followup_field_names=_as_str_list(deck.get("followup_field_names"), ["Wiedervorlage"]),
        create_only_after_paperless_success=_as_bool(deck.get("create_only_after_paperless_success"), True),
        require_document_id=_as_bool(deck.get("require_document_id"), True),
        require_deck_success_for_trash=_as_bool(deck.get("require_deck_success_for_trash"), True),
        todo_label=str(deck.get("todo_label", "Todo")),
        todo_label_color=str(deck.get("todo_label_color", "31CC7C")),
        auto_create_label=_as_bool(deck.get("auto_create_label"), True),
        title_template=str(deck.get("title_template", "Wiedervorlage: {document_title}")),
        description_template=str(deck.get("description_template", "{paperless_url}\n\n--- Erste Seite ---\n{first_page_text}")),
        max_first_page_chars=_as_int(deck.get("max_first_page_chars"), 4000),
        due_time=str(deck.get("due_time", "09:00")),
        timezone=str(deck.get("timezone", "Europe/Berlin")),
        default_effort=str(deck.get("default_effort", "")),
        effort_holiday_state=str(deck.get("effort_holiday_state", "BE")),
        http_timeout_seconds=_as_int(deck.get("http_timeout_seconds"), 30),
        routes=_as_deck_routes(deck.get("routes")),
    )
    if cfg.deck.enabled:
        _load_env_file(cfg.deck.secrets_file)
    cfg.import_ = ImportConfig(
        inbox_dir=expand_path(imp.get("inbox_dir") or imp.get("watch_dir") or "~/Documents/nc.5st.eu/paperless_ausgang"),
        pattern=str(imp.get("pattern", "img*.pdf")),
        min_age_seconds=_as_int(imp.get("min_age_seconds"), 60),
        rename_with_birthdate=_as_bool(imp.get("rename_with_birthdate"), True),
        date_format=str(imp.get("date_format", "%Y-%m-%d_%H-%M-%S")),
        set_created_from_birthdate=_as_bool(imp.get("set_created_from_birthdate"), True),
        set_title_from_filename=_as_bool(imp.get("set_title_from_filename"), True),
        default_tag=str(imp.get("default_tag", "Posteingang")),
        default_tag_from_parent_folder=_as_bool(imp.get("default_tag_from_parent_folder"), False),
        prevent_duplicates=_as_bool(imp.get("prevent_duplicates"), False),
        state_file=expand_path(imp.get("state_file") or (xdg_state_home() / APP_NAME / "uploaded.jsonl")),
        wait_for_task=_as_bool(imp.get("wait_for_task"), True),
        trash_after_success=_as_bool(imp.get("trash_after_success"), True),
        task_wait_timeout_seconds=_as_int(imp.get("task_wait_timeout_seconds"), 240),
        task_wait_interval_seconds=_as_int(imp.get("task_wait_interval_seconds"), 1),
    )
    cfg.gui = GuiConfig(
        enabled=_as_bool(gui.get("enabled"), True),
        auto_for_explicit_files=_as_bool(gui.get("auto_for_explicit_files"), True),
        preload_paperless_metadata=_as_bool(gui.get("preload_paperless_metadata"), True),
        confirm_before_upload=_as_bool(gui.get("confirm_before_upload"), True),
        viewer_mode=str(gui.get("viewer_mode", "internal")),
        split_ratio=list(gui.get("split_ratio", [50, 50]) or [50, 50]),
        close_after_success=_as_bool(gui.get("close_after_success"), True),
        close_after_seconds=_as_int(gui.get("close_after_seconds"), 2),
    )
    cfg.ocr = OcrConfig(
        enabled=_as_bool(ocr.get("enabled"), True),
        mode=str(ocr.get("mode", "auto")).strip().lower(),
        archive_engine=str(ocr.get("archive_engine", "ocrmypdf")).strip().lower(),
        assist_engine=str(ocr.get("assist_engine", "none")).strip().lower(),
        languages=_as_str_list(ocr.get("languages"), ["deu", "eng"]),
        cache_dir=expand_path(ocr.get("cache_dir") or (xdg_cache_home() / APP_NAME / "ocr")),
        upload=str(ocr.get("upload", "ocr_pdf")).strip().lower(),
        jobs=_as_int(ocr.get("jobs"), 0),
        output_type=str(ocr.get("output_type", "pdfa")),
        rotate_pages=_as_bool(ocr.get("rotate_pages"), True),
        deskew=_as_bool(ocr.get("deskew"), True),
        clean=_as_bool(ocr.get("clean"), True),
        sidecar_text=_as_bool(ocr.get("sidecar_text"), True),
        min_text_chars=_as_int(ocr.get("min_text_chars"), 40),
        text_probe_pages=_as_int(ocr.get("text_probe_pages"), 3),
        timeout_seconds=_as_int(ocr.get("timeout_seconds"), 0),
        fail_on_error=_as_bool(ocr.get("fail_on_error"), True),
    )
    cfg.custom = CustomConfig(
        field_nextcloud_web_url_id=_optional_int(
            _first_present(custom, "field_nextcloud_web_url_id", "custom_field_nextcloud_web_url_id")
        ),
        field_nextcloud_cloud_path_id=_optional_int(
            _first_present(
                custom,
                "field_nextcloud_cloud_path_id",
                "custom_field_nextcloud_cloud_path_id",
                "custom_field_nextcloud_path_id",
            )
        ),
        field_nextcloud_webdav_url_id=_optional_int(
            _first_present(
                custom, "field_nextcloud_webdav_url_id", "custom_field_nextcloud_webdav_url_id"
            )
        ),
        field_nextcloud_fileid_id=_optional_int(
            _first_present(custom, "field_nextcloud_fileid_id", "custom_field_nextcloud_fileid_id")
        ),
        field_nextcloud_etag_id=_optional_int(
            _first_present(custom, "field_nextcloud_etag_id", "custom_field_nextcloud_etag_id")
        ),
        field_local_path_id=_optional_int(
            _first_present(custom, "field_local_path_id", "custom_field_local_path_id")
        ),
        field_sha256_id=_optional_int(
            _first_present(custom, "field_sha256_id", "custom_field_sha256_id")
        ),
        field_original_path_id=_optional_int(
            _first_present(custom, "field_original_path_id", "custom_field_original_path_id")
        ),
        field_birthtime_id=_optional_int(
            _first_present(custom, "field_birthtime_id", "custom_field_birthtime_id")
        ),
        field_deck_card_url_id=_optional_int(custom.get("field_deck_card_url_id")),
        field_deck_card_id_id=_optional_int(custom.get("field_deck_card_id_id")),
        field_global_document_id_id=_optional_int(custom.get("field_global_document_id_id")),
        field_process_id_id=_optional_int(custom.get("field_process_id_id")),
        global_document_id_template=str(
            custom.get(
                "global_document_id_template",
                "urn:paperless:{paperless_host}:document:{paperless_document_id}",
            )
        ),
        process_id_template=str(custom.get("process_id_template", "{global_document_id}")),
        require_backlink_update_for_trash=_as_bool(
            custom.get("require_backlink_update_for_trash"), False
        ),
        custom_field_extraction_rules=_as_custom_field_extraction_rules(
            _first_present(
                custom,
                "custom_field_extraction_rules",
                "custom_field_autofill",
                "autofill_rules",
                "extraction_rules",
                default=[],
            )
        ),
    )
    return cfg


def write_example_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    example = Path(__file__).resolve().parent.parent / "configs" / "config.example.yaml"
    if example.exists():
        path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
