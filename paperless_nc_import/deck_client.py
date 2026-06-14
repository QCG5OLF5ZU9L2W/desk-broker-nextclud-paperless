from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, time
from pathlib import Path
import os
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .config import DeckConfig, DeckRouteConfig
from .effort import EffortParseError, compute_start_datetime, parse_effort
from .models import FileInfo, ImportSelection, ImportResult, Metadata, NextcloudReference
from .ocr import OcrProcessor


class DeckError(RuntimeError):
    pass


@dataclass(slots=True)
class DeckResolvedRoute:
    server_url: str
    username: str
    app_password: str
    board_id: int = 0
    stack_id: int = 0
    route_name: str = ""


@dataclass(slots=True)
class DeckCardResult:
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

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _norm_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _norm_path(value: str | Path) -> str:
    return str(Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve(strict=False))


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Paperless date custom fields are usually YYYY-MM-DD.  Accept common GUI display too.
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _deck_due_datetime(d: date, due_time: str, timezone_name: str) -> datetime:
    try:
        hh, mm = [int(x) for x in (due_time or "09:00").split(":", 1)]
    except Exception:
        hh, mm = 9, 0
    try:
        zone = ZoneInfo(timezone_name or "Europe/Berlin")
    except Exception:
        zone = ZoneInfo("Europe/Berlin")
    return datetime.combine(d, time(hour=hh, minute=mm), tzinfo=zone)


def _field_names(metadata: Metadata) -> dict[int, str]:
    return {f.id: f.name for f in metadata.custom_fields}


def find_followup_date(selection: ImportSelection, metadata: Metadata, cfg: DeckConfig) -> tuple[date | None, str]:
    """Return the Wiedervorlage date from selected Paperless custom fields.

    The importer never guesses a Nextcloud instance here.  It only looks at the
    Paperless custom fields already chosen in the current import.  Matching by
    ID is preferred; matching by name is only a convenience fallback.
    """
    names = _field_names(metadata)
    ids = set(cfg.followup_field_ids or [])
    wanted_names = {x.strip().casefold() for x in (cfg.followup_field_names or []) if x.strip()}
    for field_id, value in selection.custom_fields.items():
        try:
            field_id_i = int(field_id)
        except Exception:
            continue
        name = names.get(field_id_i, "")
        is_match = field_id_i in ids or (name and name.casefold() in wanted_names)
        if not is_match:
            continue
        d = _as_date(value)
        if d:
            return d, name or str(field_id_i)
        return None, name or str(field_id_i)
    return None, ""


def first_page_text(file_info: FileInfo, result: ImportResult, cfg) -> str:
    """Get first-page text from OCR sidecar if possible, otherwise pdftotext page 1."""
    sidecar = result.ocr_sidecar_txt
    if sidecar and Path(sidecar).exists():
        text = Path(sidecar).read_text(encoding="utf-8", errors="replace")
        first = text.split("\f", 1)[0].strip()
        if first:
            return first
    pdf = result.ocr_upload_path or result.ocr_output_pdf or file_info.current_path
    try:
        return OcrProcessor(cfg.ocr).extract_text(Path(pdf), max_pages=1).strip()
    except Exception:
        return ""


def resolve_deck_route(
    deck_cfg: DeckConfig,
    nc: NextcloudReference | None,
    *,
    board_id_override: int | None = None,
    stack_id_override: int | None = None,
    require_target: bool = True,
) -> tuple[DeckResolvedRoute | None, str]:
    """Resolve Deck access for the Nextcloud mount of the selected file.

    The Nextcloud instance is always derived from the file path / nextcloud.cfg.
    Board and stack can be selected per import in the GUI.  YAML board_id/stack_id
    remain optional defaults only.
    """
    if not nc or not nc.mount:
        return None, "Datei liegt in keiner erkannten Nextcloud-Sync-Wurzel."
    mount = nc.mount
    server = _norm_url(mount.server_url)
    user = mount.user or ""
    mount_local_root = _norm_path(mount.local_root)
    cloud_root = mount.remote_root or "/"

    matched_without_credentials: list[str] = []

    def matches(route: DeckRouteConfig) -> bool:
        if route.match_server and _norm_url(route.match_server) != server:
            return False
        if route.match_user and route.match_user != user:
            return False
        if route.match_local_root:
            route_root = _norm_path(route.match_local_root)
            if route_root != mount_local_root:
                return False
        if route.match_remote_root and route.match_remote_root != cloud_root:
            return False
        return True

    for route in deck_cfg.routes:
        if not matches(route):
            continue
        username = route.username or user
        password = route.app_password
        if route.app_password_env:
            password = os.environ.get(route.app_password_env, password)
        if not username:
            matched_without_credentials.append(
                f"Route {route.name or '<ohne Namen>'} passt, aber username fehlt."
            )
            continue
        if not password:
            env_hint = f" Umgebungsvariable {route.app_password_env!r} ist nicht gesetzt." if route.app_password_env else ""
            matched_without_credentials.append(
                f"Route {route.name or '<ohne Namen>'} passt, aber App-Passwort fehlt.{env_hint}"
            )
            continue

        board_id = int(board_id_override or route.board_id or 0)
        stack_id = int(stack_id_override or route.stack_id or 0)
        if require_target and (not board_id or not stack_id):
            matched_without_credentials.append(
                f"Route {route.name or '<ohne Namen>'} passt, aber Board/Stack wurde nicht gewählt."
            )
            continue
        return DeckResolvedRoute(
            server_url=server,
            username=username,
            app_password=password,
            board_id=board_id,
            stack_id=stack_id,
            route_name=route.name,
        ), ""

    if matched_without_credentials:
        return None, "; ".join(matched_without_credentials)
    return None, (
        "Keine passende Deck-Route für die erkannte Nextcloud-Sync-Wurzel. "
        f"Erkannt: local_root={mount_local_root}, server={server}, user={user}, remote={cloud_root}."
    )


class DeckClient:
    def __init__(self, route: DeckResolvedRoute, *, timeout_seconds: int = 30) -> None:
        self.route = route
        self.timeout_seconds = timeout_seconds
        self.base = route.server_url.rstrip("/") + "/index.php/apps/deck/api/v1.0"
        self.session = requests.Session()
        self.session.auth = (route.username, route.app_password)
        self.session.headers.update({"OCS-APIRequest": "true", "Accept": "application/json"})

    def _url(self, endpoint: str) -> str:
        return self.base + "/" + endpoint.lstrip("/")

    def get(self, endpoint: str) -> Any:
        r = self.session.get(self._url(endpoint), timeout=self.timeout_seconds)
        if r.status_code >= 400:
            raise DeckError(f"GET {endpoint} fehlgeschlagen: HTTP {r.status_code}: {r.text[:500]}")
        return r.json() if r.text.strip() else {}

    def post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        r = self.session.post(
            self._url(endpoint),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout_seconds,
        )
        if r.status_code >= 400:
            raise DeckError(f"POST {endpoint} fehlgeschlagen: HTTP {r.status_code}: {r.text[:500]}")
        return r.json() if r.text.strip() else {}

    def put(self, endpoint: str, payload: dict[str, Any]) -> Any:
        r = self.session.put(
            self._url(endpoint),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout_seconds,
        )
        if r.status_code >= 400:
            raise DeckError(f"PUT {endpoint} fehlgeschlagen: HTTP {r.status_code}: {r.text[:500]}")
        return r.json() if r.text.strip() else {}

    def boards(self) -> list[dict[str, Any]]:
        data = self.get("boards")
        return data if isinstance(data, list) else []

    def stacks(self, board_id: int) -> list[dict[str, Any]]:
        data = self.get(f"boards/{int(board_id)}/stacks")
        return data if isinstance(data, list) else []

    def board(self) -> dict[str, Any]:
        if not self.route.board_id:
            return {}
        data = self.get(f"boards/{self.route.board_id}")
        return data if isinstance(data, dict) else {}

    def ensure_label(self, title: str, color: str, *, auto_create: bool = True) -> int | None:
        wanted = title.strip().casefold()
        if not wanted:
            return None
        board = self.board()
        for label in board.get("labels") or []:
            if str(label.get("title") or "").strip().casefold() == wanted:
                try:
                    return int(label.get("id"))
                except Exception:
                    return None
        if not auto_create:
            return None
        data = self.post(f"boards/{self.route.board_id}/labels", {"title": title, "color": color.lstrip("#") or "31CC7C"})
        if isinstance(data, dict) and data.get("id"):
            return int(data["id"])
        return None

    def create_card(
        self,
        *,
        title: str,
        description: str,
        due_date: datetime,
        start_date: datetime | None = None,
    ) -> dict[str, Any]:
        payload = {
            "title": title[:255],
            "type": "plain",
            "order": 999,
            "description": description,
            "duedate": due_date.isoformat(),
        }
        if start_date is not None:
            payload["startdate"] = start_date.isoformat()
        data = self.post(f"boards/{self.route.board_id}/stacks/{self.route.stack_id}/cards", payload)
        return data if isinstance(data, dict) else {"raw": data}

    def assign_label(self, card_id: int, label_id: int) -> None:
        self.put(
            f"boards/{self.route.board_id}/stacks/{self.route.stack_id}/cards/{card_id}/assignLabel",
            {"labelId": label_id},
        )

    def card_url(self, card_id: int) -> str:
        # Web route can vary between Deck versions, but this is the commonly used canonical form.
        return f"{self.route.server_url.rstrip('/')}/apps/deck/#/board/{self.route.board_id}/card/{card_id}"


def build_description(
    *,
    cfg: DeckConfig,
    paperless_url: str,
    first_page: str,
    file_info: FileInfo,
    result: ImportResult,
    effort_label: str = "",
    start_date: str = "",
) -> str:
    first_page = (first_page or "").strip()
    if cfg.max_first_page_chars and len(first_page) > cfg.max_first_page_chars:
        first_page = first_page[: cfg.max_first_page_chars].rstrip() + "\n…"
    nc = file_info.nextcloud
    values = {
        "paperless_url": paperless_url,
        "paperless_document_id": result.document_id or "",
        "global_document_id": result.global_document_id or "",
        "process_id": result.process_id or "",
        "nextcloud_web_link": nc.web_link if nc else "",
        "nextcloud_internal_link": nc.internal_link if nc else "",
        "nextcloud_cloud_path": nc.cloud_path if nc else "",
        "first_page_text": first_page or "[Keine Textschicht/OCR-Seitentext gefunden.]",
        "deck_effort": effort_label,
        "deck_start_date": start_date,
    }
    marker = (
        "<!-- paperless-nc-import\n"
        f"paperless_document_id: {values['paperless_document_id']}\n"
        f"global_document_id: {values['global_document_id']}\n"
        f"process_id: {values['process_id']}\n"
        f"paperless_url: {paperless_url}\n"
        "-->"
    )
    template = cfg.description_template or "{paperless_url}\n\n--- Erste Seite ---\n{first_page_text}"
    try:
        body = template.format(**values)
    except Exception:
        body = f"{paperless_url}\n\n--- Erste Seite ---\n{values['first_page_text']}"
    return marker + "\n\n" + body


def maybe_create_followup_card(
    *,
    cfg,
    file_info: FileInfo,
    selection: ImportSelection,
    metadata: Metadata,
    result: ImportResult,
) -> DeckCardResult:
    deck_cfg = cfg.deck
    out = DeckCardResult()
    if not deck_cfg.enabled:
        out.skipped = True
        out.reason = "Deck-Integration deaktiviert."
        return out
    followup_date, followup_field = find_followup_date(selection, metadata, deck_cfg)
    if not followup_field:
        out.skipped = True
        out.reason = "Kein Wiedervorlage-Custom-Field gesetzt."
        return out
    if not followup_date:
        out.skipped = True
        out.reason = f"Wiedervorlage-Feld {followup_field!r} gesetzt, aber kein gültiges Datum."
        return out
    out.attempted = True
    paperless_resolved = bool(result.document_id) and ((result.task_success and not result.task_failed) or result.duplicate_detected)
    if deck_cfg.create_only_after_paperless_success and not paperless_resolved:
        out.reason = "Paperless-Dokument nicht sicher aufgelöst; Deck-Karte wird nicht erstellt."
        return out
    if deck_cfg.require_document_id and not result.document_id:
        out.reason = "Keine sichere Paperless-Dokument-ID; Deck-Karte wird nicht erstellt."
        return out
    route, route_reason = resolve_deck_route(
        deck_cfg,
        file_info.nextcloud,
        board_id_override=selection.deck_board_id,
        stack_id_override=selection.deck_stack_id,
        require_target=True,
    )
    if not route:
        out.reason = route_reason
        return out

    out.server_url = route.server_url
    out.username = route.username
    out.board_id = route.board_id
    out.stack_id = route.stack_id
    out.route_name = route.route_name
    due_dt = _deck_due_datetime(followup_date, deck_cfg.due_time, deck_cfg.timezone)
    out.due_date = due_dt.isoformat()
    raw_effort = (selection.deck_effort or deck_cfg.default_effort or "").strip()
    effort = None
    start_dt = None
    if raw_effort:
        try:
            effort = parse_effort(raw_effort)
            start_dt = compute_start_datetime(due_dt, effort, deck_cfg.effort_holiday_state)
            out.effort = effort.label
            if start_dt is not None:
                out.start_date = start_dt.isoformat()
        except EffortParseError as exc:
            raise DeckError(str(exc)) from exc
    title = deck_cfg.title_template or "Wiedervorlage: {document_title}"
    try:
        out.title = title.format(document_title=selection.title, paperless_document_id=result.document_id or "")[:255]
    except Exception:
        out.title = f"Wiedervorlage: {selection.title}"[:255]
    first_page = first_page_text(file_info, result, cfg)
    description = build_description(
        cfg=deck_cfg,
        paperless_url=result.paperless_url,
        first_page=first_page,
        file_info=file_info,
        result=result,
        effort_label=out.effort,
        start_date=out.start_date,
    )
    out.marker = result.global_document_id or str(result.document_id or "")

    client = DeckClient(route, timeout_seconds=deck_cfg.http_timeout_seconds)
    response = client.create_card(title=out.title, description=description, due_date=due_dt, start_date=start_dt)
    out.response = response
    card_id = response.get("id") if isinstance(response, dict) else None
    if not card_id:
        raise DeckError(f"Deck-Karte angelegt, aber keine Karten-ID erhalten: {response}")
    out.card_id = int(card_id)
    out.card_url = client.card_url(out.card_id)
    if deck_cfg.todo_label:
        label_id = client.ensure_label(deck_cfg.todo_label, deck_cfg.todo_label_color, auto_create=deck_cfg.auto_create_label)
        if label_id:
            out.label_id = label_id
            out.label_title = deck_cfg.todo_label
            client.assign_label(out.card_id, label_id)
    out.created = True
    out.reason = "Deck-Karte angelegt."
    return out
