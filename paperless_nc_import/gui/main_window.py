from __future__ import annotations

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QTextEdit

import logging

from datetime import date, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..deck_client import DeckClient, resolve_deck_route, find_followup_date
from ..effort import EffortParseError, parse_effort
from ..extraction import extract_custom_field_value

LOG = logging.getLogger(__name__)
from ..fs_utils import collect_input_files
from ..importer import Importer
from ..logging_utils import AppLogger
from ..models import CustomField, Entity, FileInfo, ImportResult, ImportSelection, Metadata
from ..nextcloud_config import read_nextcloud_mounts
from ..ocr import OcrError, OcrProcessor
from ..paperless_client import PaperlessClient
from ..trash import move_to_trash
from .pdf_viewer import PdfViewer
from .widgets import CustomFieldEditor, DateDeadlineWidget, EntityPicker, SubmitLineEdit, TagSelector


class MetadataWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, cfg: AppConfig, use_cache: bool) -> None:
        super().__init__()
        self.cfg = cfg
        self.use_cache = use_cache

    def run(self) -> None:
        try:
            client = PaperlessClient(self.cfg.paperless)
            metadata = client.load_metadata(use_cache=self.use_cache)
            self.finished.emit(metadata)
        except Exception as exc:
            self.failed.emit(str(exc))



class OcrWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int)

    def __init__(self, cfg: AppConfig, path: Path, sha256: str, force: bool) -> None:
        super().__init__()
        self.cfg = cfg
        self.path = path
        self.sha256 = sha256
        self.force = force

    def run(self) -> None:
        try:
            result = OcrProcessor(self.cfg.ocr).prepare(
                self.path,
                sha256=self.sha256,
                force=self.force,
                progress=lambda message, percent: self.progress.emit(message, percent),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ImportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int)

    def __init__(self, importer: Importer, file_info: FileInfo, selection: ImportSelection, metadata: Metadata, dry_run: bool) -> None:
        super().__init__()
        self.importer = importer
        self.file_info = file_info
        self.selection = selection
        self.metadata = metadata
        self.dry_run = dry_run

    def run(self) -> None:
        try:
            result = self.importer.import_one(
                self.file_info,
                self.selection,
                self.metadata,
                dry_run=self.dry_run,
                progress=lambda message, percent: self.progress.emit(message, percent),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, logger: AppLogger, files: list[Path], *, dry_run: bool, no_cache: bool) -> None:
        super().__init__()
        self.cfg = cfg
        self.logger = logger
        self.files = files
        self.dry_run = dry_run
        self.no_cache = no_cache
        self.metadata = Metadata()
        self.client = PaperlessClient(cfg.paperless)
        self.mounts = read_nextcloud_mounts(cfg.nextcloud)
        self.importer = Importer(cfg, self.client)
        self.file_infos = [self.importer.build_file_info(p, self.mounts) for p in self.files]
        self.current_info: FileInfo | None = self.file_infos[0] if self.file_infos else None
        self.custom_field_map: dict[int, Any] = {}
        self.selected_custom_field: CustomField | None = None
        self.ocr_result = None
        self._extraction_text_cache_key: tuple[str, str, float] | None = None
        self._extraction_text_cache = ""
        self.deck_route_base = None
        self.deck_boards: list[dict[str, Any]] = []
        self.deck_stacks: list[dict[str, Any]] = []

        self.setWindowTitle("Paperless Nextcloud Import")
        self.resize(1500, 950)
        self._build_ui()
        self._auto_ocr_started_once = False
        QTimer.singleShot(5000, self._auto_run_ocr_if_missing_text_layer)
        self._fill_file_values()
        self._fill_nextcloud_values()
        self._auto_ocr_started_once = False
        QTimer.singleShot(600, self.check_ocr)
        QTimer.singleShot(1300, self._auto_run_ocr_if_missing_text_layer)
        QTimer.singleShot(5000, self._auto_run_ocr_if_missing_text_layer)
        QTimer.singleShot(7000, self._prefill_document_date_from_extraction)
        if self.current_info:
            self.pdf.load(self.current_info.current_path)
        self._start_metadata_load()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter, 1)

        # Paperless-like orientation: metadata/actions on the left, document viewer on the right.
        # The earlier prototype had this reversed and felt unlike Paperless.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.form_host = QWidget()
        self.form = QVBoxLayout(self.form_host)
        self.form.setContentsMargins(14, 14, 14, 14)
        self.scroll.setWidget(self.form_host)
        self.splitter.addWidget(self.scroll)

        self.pdf = PdfViewer()
        self.splitter.addWidget(self.pdf)
        self.splitter.setSizes([760, 740])

        self._section_file()
        self._section_ocr()
        self._section_paperless()
        self._section_custom_fields()
        self._section_deck()
        self._section_nextcloud()
        self._section_options()
        self._section_log()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.dry_btn = QPushButton("Dry-run")
        self.import_btn = QPushButton("Importieren")
        self.close_btn = QPushButton("Schließen")
        self.dry_btn.clicked.connect(lambda: self.run_import(True))
        self.import_btn.clicked.connect(lambda: self.run_import(False))
        self.close_btn.clicked.connect(self.close)
        buttons.addWidget(self.dry_btn)
        buttons.addWidget(self.import_btn)
        buttons.addWidget(self.close_btn)
        root.addLayout(buttons)
        self.setCentralWidget(central)

    def _add_heading(self, text: str, hint: str = "") -> None:
        title = QLabel(text)
        title.setStyleSheet("font-size: 22px; font-weight: 700; margin-top: 12px;")
        self.form.addWidget(title)
        if hint:
            h = QLabel(hint)
            h.setWordWrap(True)
            self.form.addWidget(h)

    def _section_file(self) -> None:
        self._add_heading("1. Dokument", "Ermittelte Dateidaten; Dokumentdatum kann angepasst werden.")
        fl = QFormLayout()
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.title_edit = QLineEdit()
        self.created_widget = DateDeadlineWidget(allow_bgb=False)
        self.created_widget.changed.connect(lambda: self._refresh_custom_context() if hasattr(self, "custom_editor") else None)
        self.asn_edit = QLineEdit()
        fl.addRow("Datei", self.file_path)
        fl.addRow("Titel", self.title_edit)
        fl.addRow("Date created", self.created_widget)
        fl.addRow("ASN", self.asn_edit)
        self.form.addLayout(fl)

    def _section_ocr(self) -> None:
        self._add_heading("2. OCR", "Lokale OCR vor dem Upload: erzeugt bei reinen Scans eine Textschicht und eine Textdatei für Kopieren/Feldvorschläge.")
        self.ocr_status = QLabel("Noch nicht geprüft.")
        self.ocr_status.setWordWrap(True)
        self.ocr_progress = QProgressBar()
        self.ocr_progress.setRange(0, 100)
        self.ocr_progress.setValue(0)
        self.ocr_progress.setFormat("OCR: bereit")
        self.ocr_use_upload = QCheckBox("OCR-PDF hochladen, wenn erzeugt")
        self.ocr_use_upload.setChecked(self.cfg.ocr.upload == "ocr_pdf")
        row = QHBoxLayout()
        self.ocr_check_btn = QPushButton("Textschicht prüfen")
        self.ocr_run_btn = QPushButton("OCR starten")
        self.ocr_force_btn = QPushButton("OCR erzwingen")
        self.ocr_check_btn.clicked.connect(self.check_ocr)
        self.ocr_run_btn.clicked.connect(lambda: self.run_ocr(False))
        self.ocr_force_btn.clicked.connect(lambda: self.run_ocr(True))
        row.addWidget(self.ocr_check_btn)
        row.addWidget(self.ocr_run_btn)
        row.addWidget(self.ocr_force_btn)
        row.addStretch(1)
        self.form.addWidget(self.ocr_status)
        self.form.addWidget(self.ocr_progress)
        self.form.addWidget(self.ocr_use_upload)
        self.form.addLayout(row)

    def _section_paperless(self) -> None:
        self._add_heading("3. Paperless-Metadaten", "Paperless-ähnlich: Posteingang ist vorausgewählt; Herkunft/Nextcloud wird nicht als Tag geraten. Enter übernimmt den ersten Treffer.")
        self.tags = TagSelector()
        self.form.addWidget(self.tags)
        self.correspondent = EntityPicker("Korrespondent")
        self.document_type = EntityPicker("Dokumenttyp")
        self.storage_path = EntityPicker("Storage Path")
        self.form.addWidget(self.correspondent)
        self.form.addWidget(self.document_type)
        self.form.addWidget(self.storage_path)

    def _section_custom_fields(self) -> None:
        self._add_heading("4. Custom Fields", "Typgerecht befüllen. Quellen werden nach Feldname und Feldtyp eingegrenzt; IBAN mit Prüfziffer.")
        self.custom_selected_label = QLabel("Ausgewählte Custom Fields: —")
        self.custom_search = SubmitLineEdit()
        self.custom_search.setPlaceholderText("Custom Fields suchen; Enter wählt ersten Treffer")
        self.custom_list = QListWidget()
        self.custom_list.setMaximumHeight(180)
        self.custom_editor = CustomFieldEditor([])
        self.custom_editor.take.clicked.connect(self.take_custom_value)
        self.custom_editor.remove.clicked.connect(self.remove_custom_value)
        self.custom_search.textChanged.connect(self.refilter_custom_fields)
        self.custom_search.submitted.connect(self.select_first_custom_field)
        self.custom_list.itemActivated.connect(self.activate_custom_item)
        self.custom_list.itemClicked.connect(self.activate_custom_item)
        self.form.addWidget(self.custom_selected_label)
        self.form.addWidget(self.custom_search)
        self.form.addWidget(self.custom_list)
        self.form.addWidget(self.custom_editor)

    def _section_deck(self) -> None:
        self.deck_section = QWidget()
        layout = QVBoxLayout(self.deck_section)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("5. Deck-Wiedervorlage")
        title.setStyleSheet("font-size: 22px; font-weight: 700; margin-top: 12px;")
        layout.addWidget(title)
        hint = QLabel("Erscheint nur, wenn das Wiedervorlage-Custom-Field gesetzt ist. Board/Stack werden aus der realen Deck-API geladen.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.deck_status = QLabel("Deck-Ziel noch nicht geladen.")
        self.deck_status.setWordWrap(True)
        self.deck_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.deck_board_combo = QComboBox()
        self.deck_stack_combo = QComboBox()
        self.deck_effort_edit = QLineEdit(self.cfg.deck.default_effort)
        self.deck_effort_edit.setPlaceholderText("z.B. 5d = 5 Arbeitstage, 3h = 3 Stunden, 30m, 10kt")
        self.deck_effort_note = QLabel("Vorlauf/Aufwand legt den Deck-Startzeitpunkt vor dem Fälligkeitsdatum fest. Leer = kein Startdatum.")
        self.deck_effort_note.setWordWrap(True)
        self.deck_effort_edit.editingFinished.connect(self.validate_deck_effort)
        self.deck_reload_btn = QPushButton("Deck-Ziele laden")
        self.deck_test_btn = QPushButton("Verbindung prüfen")
        self.deck_reload_btn.clicked.connect(lambda: self.load_deck_targets(silent=False))
        self.deck_test_btn.clicked.connect(lambda: self.load_deck_targets(silent=False))
        self.deck_board_combo.currentIndexChanged.connect(lambda _: self._deck_board_changed())
        form = QFormLayout()
        form.addRow("Status", self.deck_status)
        form.addRow("Board", self.deck_board_combo)
        form.addRow("Stack", self.deck_stack_combo)
        form.addRow("Vorlauf/Aufwand", self.deck_effort_edit)
        form.addRow("", self.deck_effort_note)
        buttons = QHBoxLayout()
        buttons.addWidget(self.deck_reload_btn)
        buttons.addWidget(self.deck_test_btn)
        buttons.addStretch(1)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.form.addWidget(self.deck_section)
        self.deck_section.setVisible(False)

    def _section_nextcloud(self) -> None:
        self._add_heading("6. Nextcloud-Rückverweis", "Herkunft wird als Rückverweis/Custom Field genutzt, aber nicht als Tag vorausgewählt.")
        self.nextcloud_status = QLabel("—")
        self.nextcloud_status.setWordWrap(True)
        self.form.addWidget(self.nextcloud_status)
        self.nc_fields: dict[str, QLineEdit] = {}
        nc_form = QFormLayout()
        for key, label in [
            ("local", "lokale Sync-Wurzel"),
            ("server", "Nextcloud Server"),
            ("remote", "Remote-Wurzel"),
            ("cloud", "Cloud-Pfad"),
            ("web", "Web-Link"),
            ("internal", "Interner Link"),
            ("webdav", "WebDAV"),
            ("fileid", "FileID"),
            ("etag", "ETag"),
            ("journal", "Sync-Journal"),
        ]:
            edit = QLineEdit()
            edit.setReadOnly(True)
            self.nc_fields[key] = edit
            nc_form.addRow(label, edit)
        self.form.addLayout(nc_form)

    def _section_options(self) -> None:
        self._add_heading("7. Optionen")
        self.option_dry = QLabel("Dry-run ist aktiv" if self.dry_run else "Echter Import beim Klick auf Importieren")
        self.form.addWidget(self.option_dry)
        trash_text = "Quelldatei wird nach Paperless-Dokument-ID in den Papierkorb verschoben" if self.cfg.import_.trash_after_success else "Quelldatei bleibt lokal erhalten"
        self.form.addWidget(QLabel(trash_text))

    def _section_log(self) -> None:
        self._add_heading("8. Log")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(180)
        self.log.setPlainText(self.logger.text())
        self.form.addWidget(self.log)

    def _fill_file_values(self) -> None:
        if not self.current_info:
            return
        info = self.current_info
        self.file_path.setText(str(info.current_path))
        self.title_edit.setText(info.title)
        self.created_widget.set_base_dates({"Birthtime": info.birthtime.date()})
        self.created_widget.set_date(info.created.date())

    def _fill_nextcloud_values(self) -> None:
        if not self.current_info or not self.current_info.nextcloud:
            return
        nc = self.current_info.nextcloud
        mount = nc.mount
        self.nextcloud_status.setText(nc.status)
        self.nc_fields["local"].setText(str(mount.local_root) if mount else "")
        self.nc_fields["server"].setText(mount.server_url if mount else "")
        self.nc_fields["remote"].setText(mount.remote_root if mount else "")
        self.nc_fields["cloud"].setText(nc.cloud_path)
        self.nc_fields["web"].setText(nc.web_link)
        self.nc_fields["internal"].setText(nc.internal_link)
        self.nc_fields["webdav"].setText(nc.webdav_url)
        self.nc_fields["fileid"].setText(nc.file_id)
        self.nc_fields["etag"].setText(nc.etag)
        self.nc_fields["journal"].setText(str(nc.journal_path or ""))
        self.load_deck_targets(silent=True)

    def load_deck_targets(self, *, silent: bool = False) -> None:
        if not hasattr(self, "deck_status"):
            return
        self.deck_board_combo.blockSignals(True)
        self.deck_stack_combo.blockSignals(True)
        self.deck_board_combo.clear()
        self.deck_stack_combo.clear()
        self.deck_boards = []
        self.deck_stacks = []
        self.deck_route_base = None
        self.deck_board_combo.blockSignals(False)
        self.deck_stack_combo.blockSignals(False)

        if not self.cfg.deck.enabled:
            self.deck_status.setText("Deck ist in der Konfiguration deaktiviert.")
            return
        if not self.current_info:
            self.deck_status.setText("Keine Datei geladen.")
            return
        route, reason = resolve_deck_route(self.cfg.deck, self.current_info.nextcloud, require_target=False)
        if not route:
            self.deck_status.setText(reason)
            if not silent:
                QMessageBox.warning(self, "Deck", reason)
            return
        self.deck_route_base = route
        try:
            client = DeckClient(route, timeout_seconds=self.cfg.deck.http_timeout_seconds)
            boards = client.boards()
        except Exception as exc:
            msg = f"Deck-Boards konnten nicht geladen werden: {exc}"
            self.deck_status.setText(msg)
            if not silent:
                QMessageBox.critical(self, "Deck", msg)
            return

        editable = []
        for board in boards:
            if not isinstance(board, dict) or board.get("archived") or board.get("deletedAt"):
                continue
            perms = board.get("permissions") or {}
            if perms.get("PERMISSION_EDIT"):
                editable.append(board)
        self.deck_boards = editable
        self.deck_board_combo.blockSignals(True)
        self.deck_board_combo.clear()
        for board in editable:
            title = board.get("title") or "<ohne Titel>"
            self.deck_board_combo.addItem(f"{title} (#{board.get('id')})", int(board.get("id")))
        self.deck_board_combo.blockSignals(False)
        if not editable:
            self.deck_status.setText(f"Deck verbunden mit {route.server_url} als {route.username}, aber keine editierbaren Boards gefunden.")
            return

        target_board = route.board_id or 0
        idx = -1
        if target_board:
            idx = self.deck_board_combo.findData(target_board)
        if idx < 0:
            idx = 0
        self.deck_board_combo.setCurrentIndex(idx)
        self._deck_board_changed()
        self.deck_status.setText(
            f"Deck verbunden: {route.server_url} als {route.username}. Board/Stack bitte prüfen; keine geratenen IDs."
        )

    def _deck_board_changed(self) -> None:
        if not hasattr(self, "deck_stack_combo") or not self.deck_route_base:
            return
        board_id = self.deck_board_combo.currentData()
        self.deck_stack_combo.blockSignals(True)
        self.deck_stack_combo.clear()
        self.deck_stack_combo.blockSignals(False)
        if not board_id:
            return
        try:
            client = DeckClient(self.deck_route_base, timeout_seconds=self.cfg.deck.http_timeout_seconds)
            stacks = client.stacks(int(board_id))
        except Exception as exc:
            self.deck_status.setText(f"Deck-Stacks konnten nicht geladen werden: {exc}")
            return
        visible = []
        for stack in stacks:
            if not isinstance(stack, dict) or stack.get("deletedAt"):
                continue
            visible.append(stack)
        self.deck_stacks = visible
        self.deck_stack_combo.blockSignals(True)
        self.deck_stack_combo.clear()
        for stack in visible:
            title = stack.get("title") or "<ohne Titel>"
            self.deck_stack_combo.addItem(f"{title} (#{stack.get('id')})", int(stack.get("id")))
        self.deck_stack_combo.blockSignals(False)
        target_stack = self.deck_route_base.stack_id or 0
        idx = -1
        if target_stack:
            idx = self.deck_stack_combo.findData(target_stack)
        if idx < 0 and self.deck_stack_combo.count():
            idx = 0
        if idx >= 0:
            self.deck_stack_combo.setCurrentIndex(idx)
        board_label = self.deck_board_combo.currentText() or f"#{board_id}"
        if visible:
            self.deck_status.setText(f"Deck-Ziel: {board_label} → {self.deck_stack_combo.currentText()}")
        else:
            self.deck_status.setText(f"Board {board_label} hat keine aktiven Stacks.")


    def validate_deck_effort(self) -> bool:
        if not hasattr(self, "deck_effort_edit"):
            return True
        text = self.deck_effort_edit.text().strip()
        if not text:
            self.deck_effort_note.setText("Leer = kein Deck-Startdatum. Beispiele: 5d Arbeitstage, 3h Stunden, 30m Minuten, 10kt Kalendertage.")
            return True
        try:
            spec = parse_effort(text)
        except EffortParseError as exc:
            self.deck_effort_note.setText("Ungültig: " + str(exc))
            return False
        self.deck_effort_note.setText(f"OK: {spec.label}. Deck-Startdatum wird relativ zur Wiedervorlage/Fälligkeit berechnet.")
        return True

    def ocr_progress_update(self, message: str, percent: int) -> None:
        if hasattr(self, "ocr_progress"):
            self.ocr_progress.setRange(0, 100)
            self.ocr_progress.setValue(max(0, min(100, int(percent))))
            self.ocr_progress.setFormat(f"{max(0, min(100, int(percent)))} %")
        self.ocr_status.setText(message)
        self.logger.info(message)
        self.log.setPlainText(self.logger.text())

    def check_ocr(self) -> None:
        if not self.current_info:
            return
        try:
            proc = OcrProcessor(self.cfg.ocr)
            ok, missing = proc.available()
            if not ok:
                self.ocr_status.setText("OCR nicht verfügbar. Fehlend: " + ", ".join(missing))
                return
            has_text, chars = proc.has_text_layer(self.current_info.current_path)
            if has_text:
                self.ocr_status.setText(f"Textschicht vorhanden ({chars} Zeichen in den ersten Seiten). OCR wird im Auto-Modus übersprungen.")
                self.ocr_progress.setValue(100)
                self.ocr_progress.setFormat("Text vorhanden")
            else:
                self.ocr_status.setText(f"Keine ausreichende Textschicht gefunden ({chars} Zeichen). OCR empfohlen.")
                self.ocr_progress.setValue(0)
                self.ocr_progress.setFormat("OCR empfohlen")
                if not getattr(self, "_auto_ocr_started_once", False):
                    self._auto_ocr_started_once = True
                    QTimer.singleShot(50, lambda: self.run_ocr(False))
        except Exception as exc:
            self.ocr_status.setText(f"OCR-Prüfung fehlgeschlagen: {exc}")

    def run_ocr(self, force: bool) -> None:
        if not self.current_info:
            return
        self.ocr_run_btn.setEnabled(False)
        self.ocr_force_btn.setEnabled(False)
        self.ocr_progress.setRange(0, 100)
        self.ocr_progress.setValue(1)
        self.ocr_progress.setFormat("1 %")
        self.ocr_status.setText("OCR läuft im Hintergrund ...")
        self.ocr_thread = QThread(self)
        self.ocr_worker = OcrWorker(self.cfg, self.current_info.current_path, self.current_info.sha256, force)
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.progress.connect(self.ocr_progress_update)
        self.ocr_worker.finished.connect(self.ocr_finished)
        self.ocr_worker.failed.connect(self.ocr_failed)
        self.ocr_worker.finished.connect(self.ocr_thread.quit)
        self.ocr_worker.failed.connect(self.ocr_thread.quit)
        self.ocr_worker.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_worker.failed.connect(self.ocr_worker.deleteLater)
        self.ocr_thread.finished.connect(self.ocr_thread.deleteLater)
        self.ocr_thread.start()

    def ocr_finished(self, result: object) -> None:
        self.ocr_result = result
        self.ocr_run_btn.setEnabled(True)
        self.ocr_force_btn.setEnabled(True)
        try:
            used = getattr(result, "used_ocr", False)
            upload_path = getattr(result, "upload_path", None)
            out_pdf = getattr(result, "output_pdf", None)
            before = getattr(result, "text_before_chars", 0)
            after = getattr(result, "text_after_chars", 0)
            reason = getattr(result, "reason", "")
            cache = getattr(result, "cache_hit", False)
            self.ocr_progress.setRange(0, 100)
            self.ocr_progress.setValue(100)
            self.ocr_progress.setFormat("OCR fertig")
            self.ocr_status.setText(
                f"OCR fertig: {reason}; verwendet={used}; Cache={cache}; Textzeichen {before} → {after}; Upload-Datei: {upload_path}"
            )
            if out_pdf:
                self.pdf.load(out_pdf)
            sidecar = getattr(result, "sidecar_txt", None)
            if sidecar and Path(sidecar).exists():
                try:
                    self.pdf.show_text(Path(sidecar).read_text(encoding="utf-8", errors="replace"))
                except Exception as view_exc:
                    self.logger.warning("OCR-Textanzeige konnte nicht aktualisiert werden: %s", view_exc)
            self._clear_extraction_text_cache()
            self._prefill_document_date_from_extraction()
            if self.selected_custom_field:
                self._open_custom_field(self.selected_custom_field)
        except Exception as exc:
            self.ocr_status.setText(f"OCR-Ergebnis konnte nicht angezeigt werden: {exc}")

    def ocr_failed(self, message: str) -> None:
        self.ocr_run_btn.setEnabled(True)
        self.ocr_force_btn.setEnabled(True)
        self.ocr_progress.setRange(0, 100)
        self.ocr_progress.setValue(0)
        self.ocr_progress.setFormat("OCR fehlgeschlagen")
        self.ocr_status.setText("OCR fehlgeschlagen: " + message)
        QMessageBox.critical(self, "OCR fehlgeschlagen", message)

    def _start_metadata_load(self) -> None:
        self.logger.mark("GUI-Fenster angezeigt; Paperless-Metadaten werden geladen")
        self.thread = QThread(self)
        self.worker = MetadataWorker(self.cfg, use_cache=not self.no_cache)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.metadata_loaded)
        self.worker.failed.connect(self.metadata_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def metadata_loaded(self, metadata: Metadata) -> None:
        self.metadata = metadata
        source = "Cache" if metadata.from_cache else "API"
        self.logger.mark(f"Paperless-Metadaten geladen ({source}): {len(metadata.tags)} Tags, {len(metadata.correspondents)} Korrespondenten, {len(metadata.custom_fields)} Custom Fields")
        default_selection = self.importer.default_selection(self.current_info, metadata) if self.current_info else ImportSelection()
        self.tags.set_tags(metadata.tags, default_selection.tags)
        self.correspondent.set_entities(metadata.correspondents)
        self.document_type.set_entities(metadata.document_types)
        self.storage_path.set_entities(metadata.storage_paths)
        self.custom_editor.correspondents = metadata.correspondents
        self.refilter_custom_fields()
        self._refresh_custom_context()
        self._update_deck_visibility()
        self.log.setPlainText(self.logger.text())

    def metadata_failed(self, message: str) -> None:
        self.logger.error(f"Paperless-Metadaten konnten nicht geladen werden: {message}")
        self.log.setPlainText(self.logger.text())

    def refilter_custom_fields(self) -> None:
        needle = self.custom_search.text().strip().casefold()
        self.custom_list.clear()
        values = [x for x in self.metadata.custom_fields if not needle or needle in x.name.casefold()]
        for field in values[:200]:
            item = QListWidgetItem(field.label())
            item.setData(Qt.ItemDataRole.UserRole, field)
            if field.id in self.custom_field_map:
                item.setText("✓ " + item.text())
            self.custom_list.addItem(item)
        if self.custom_list.count():
            self.custom_list.setCurrentRow(0)

    def select_first_custom_field(self) -> None:
        if self.custom_list.count():
            self.activate_custom_item(self.custom_list.item(0))

    def activate_custom_item(self, item: QListWidgetItem) -> None:
        field = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(field, CustomField):
            self._open_custom_field(field)

    def _open_custom_field(self, field: CustomField) -> None:
        self.selected_custom_field = field
        suggestions = list(self.metadata.custom_value_suggestions.get(field.id, []))
        extracted = None
        prefill_value = self.custom_field_map.get(field.id)
        if prefill_value in (None, ""):
            extracted = self._extract_custom_prefill(field)
            if extracted and extracted.value:
                prefill_value = extracted.value
        if prefill_value not in (None, "") and str(prefill_value) not in suggestions:
            suggestions.insert(0, str(prefill_value))
        self._set_custom_extraction_debug("")
        self.custom_editor.set_field(field, suggestions, prefill_value=prefill_value)
        self._refresh_custom_context()

    def _clear_extraction_text_cache(self) -> None:
        self._extraction_text_cache_key = None
        self._extraction_text_cache = ""

    def _current_extraction_text(self) -> str:
        if not self.current_info:
            return ""

        sidecar = getattr(self.ocr_result, "sidecar_txt", None) if self.ocr_result else None
        sidecar_path = Path(sidecar) if sidecar else None
        if sidecar_path and sidecar_path.exists():
            key = ("sidecar", str(sidecar_path), sidecar_path.stat().st_mtime)
            if key == self._extraction_text_cache_key:
                return self._extraction_text_cache
            text = sidecar_path.read_text(encoding="utf-8", errors="replace")
            self._extraction_text_cache_key = key
            self._extraction_text_cache = text
            return text

        path = self.current_info.current_path
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        key = ("pdf", str(path), mtime)
        if key == self._extraction_text_cache_key:
            return self._extraction_text_cache

        text = ""
        try:
            if hasattr(self.pdf, "extract_all_text"):
                text = self.pdf.extract_all_text()
        except Exception:
            text = ""
        if not text:
            try:
                text = OcrProcessor(self.cfg.ocr).extract_text(path)
            except Exception:
                text = ""

        self._extraction_text_cache_key = key
        self._extraction_text_cache = text
        return text


    def _format_extraction_match_debug(self, match):
        """Return a compact, user-visible explanation for a Custom-Field prefill."""
        if not match:
            return "Kein Extraktionsvorschlag."

        parts = []
        extractor = getattr(match, "extractor", None)
        role = getattr(match, "role", None)
        label = getattr(match, "label_normalized", None)
        confidence = getattr(match, "confidence", None)
        raw = getattr(match, "raw", None)

        if extractor:
            parts.append(f"Engine: {extractor}")
        if role:
            parts.append(f"Rolle: {role}")
        if label:
            parts.append(f"Anker: {label}")
        if confidence is not None:
            try:
                parts.append(f"Confidence: {float(confidence):.2f}")
            except Exception:
                parts.append(f"Confidence: {confidence}")
        if raw:
            raw_s = str(raw).strip().replace("\n", " ")
            if len(raw_s) > 80:
                raw_s = raw_s[:77] + "..."
            parts.append(f"Rohwert: {raw_s}")

        return " | ".join(parts) if parts else "Extraktionsvorschlag vorhanden."

    def _set_custom_extraction_debug(self, text):
        """Best-effort: show extraction provenance in the existing CustomFieldEditor if supported."""
        try:
            if hasattr(self, "custom_editor") and hasattr(self.custom_editor, "set_extraction_debug"):
                self.custom_editor.set_extraction_debug(text or "")
        except Exception:
            LOG.exception("Could not update custom extraction debug label")

    def _extract_custom_prefill(self, field: CustomField):
        if not self.cfg.extraction.enabled:
            return None
        rules = self.cfg.custom.custom_field_extraction_rules
        text = self._current_extraction_text()
        info = self.current_info
        field_role = self.cfg.extraction.field_roles.get(field.id, "")
        match = extract_custom_field_value(
            field_id=field.id,
            field_name=field.name if self.cfg.extraction.infer_roles_from_field_names else "",
            field_type=field.normalized_type,
            text=text,
            rules=rules,
            sources={
                "ocr_text": text,
                "document_text": text,
                "title": self.title_edit.text(),
                "filename": info.current_path.name if info else "",
                "path": str(info.current_path) if info else "",
            },
            field_role=field_role,
            locale=self.cfg.extraction.locale,
            use_builtin_rulesets=True,
        )
        self._set_custom_extraction_debug(self._format_extraction_match_debug(match))
        return match

    def _refresh_custom_context(self) -> None:
        info = self.current_info
        nc = info.nextcloud if info else None
        corr = self.correspondent.selected
        sources = {
            "correspondent_name": lambda: corr.name if corr else "",
            "nextcloud_internal": lambda: nc.internal_link if nc else "",
            "nextcloud_web": lambda: nc.web_link if nc else "",
            "nextcloud_cloud": lambda: nc.cloud_path if nc else "",
            "nextcloud_webdav": lambda: nc.webdav_url if nc else "",
            "local_path": lambda: str(info.current_path) if info else "",
            "sha256": lambda: info.sha256 if info else "",
            "title": lambda: self.title_edit.text(),
            "document_date": lambda: self._created_datetime(),
            "birthtime_date": lambda: info.birthtime if info else datetime.now().astimezone(),
            "today": lambda: datetime.now().astimezone(),
        }
        base_dates = {}
        if info:
            base_dates["Dokumentdatum"] = self._created_datetime().date()
            base_dates["Birthtime"] = info.birthtime.date()
        self.custom_editor.set_context(sources, base_dates)

    def _created_datetime(self) -> datetime:
        if self.current_info:
            d = self.created_widget.get_date()
            base = self.current_info.created
            return base.replace(year=d.year, month=d.month, day=d.day)
        d = self.created_widget.get_date()
        return datetime.now().astimezone().replace(year=d.year, month=d.month, day=d.day)

    def take_custom_value(self) -> None:
        field = self.custom_editor.field
        if not field:
            return
        value = self.custom_editor.value()
        if value in (None, "") and field.normalized_type != "boolean":
            QMessageBox.warning(self, "Custom Field", "Kein Wert gesetzt.")
            return
        self.custom_field_map[field.id] = value
        self.update_custom_label()
        self.refilter_custom_fields()
        self._update_deck_visibility()

    def remove_custom_value(self) -> None:
        field = self.custom_editor.field
        if field and field.id in self.custom_field_map:
            self.custom_field_map.pop(field.id, None)
            self.update_custom_label()
            self.refilter_custom_fields()
            self._update_deck_visibility()

    def update_custom_label(self) -> None:
        if not self.custom_field_map:
            self.custom_selected_label.setText("Ausgewählte Custom Fields: —")
            return
        id_to_field = {f.id: f for f in self.metadata.custom_fields}
        parts = []
        for field_id, value in self.custom_field_map.items():
            field = id_to_field.get(field_id)
            label = field.name if field else str(field_id)
            parts.append(f"{label} = {value}")
        self.custom_selected_label.setText("Ausgewählte Custom Fields: " + " | ".join(parts))


    def _followup_selected(self) -> bool:
        if not self.cfg.deck.enabled or not self.custom_field_map:
            return False
        sel = ImportSelection(custom_fields=dict(self.custom_field_map))
        followup_date, followup_field = find_followup_date(sel, self.metadata, self.cfg.deck)
        return bool(followup_field and followup_date)

    def _update_deck_visibility(self) -> None:
        if not hasattr(self, "deck_section"):
            return
        visible = self._followup_selected()
        was_visible = self.deck_section.isVisible()
        self.deck_section.setVisible(visible)
        if visible and not was_visible:
            self.load_deck_targets(silent=True)

    def collect_selection(self) -> ImportSelection:
        self.tags.add_extra()
        sel = ImportSelection(
            tags=self.tags.selected_tags(),
            new_tags=self.tags.extra_tags,
            correspondent=self.correspondent.selected,
            document_type=self.document_type.selected,
            storage_path=self.storage_path.selected,
            title=self.title_edit.text().strip(),
            created=self._created_datetime(),
            asn=self.asn_edit.text().strip(),
            custom_fields=dict(self.custom_field_map),
            deck_board_id=int(self.deck_board_combo.currentData()) if hasattr(self, "deck_board_combo") and self.deck_board_combo.currentData() else None,
            deck_stack_id=int(self.deck_stack_combo.currentData()) if hasattr(self, "deck_stack_combo") and self.deck_stack_combo.currentData() else None,
            deck_effort=self.deck_effort_edit.text().strip() if hasattr(self, "deck_effort_edit") else "",
        )
        if sel.deck_effort:
            parse_effort(sel.deck_effort)
        return sel

    def run_import(self, dry_run: bool) -> None:
        if not self.current_info:
            return
        if hasattr(self, "ocr_use_upload"):
            self.cfg.ocr.upload = "ocr_pdf" if self.ocr_use_upload.isChecked() else "original"
        try:
            selection = self.collect_selection()
        except Exception as exc:
            self.logger.error(str(exc))
            self.log.setPlainText(self.logger.text())
            QMessageBox.critical(self, "Fehler", str(exc))
            return

        self.import_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.logger.info("Import läuft im Hintergrund; warte auf Paperless-Rückmeldung ..." if not dry_run else "Dry-run läuft ...")
        self.log.setPlainText(self.logger.text())

        self.import_thread = QThread(self)
        self.import_worker = ImportWorker(self.importer, self.current_info, selection, self.metadata, dry_run)
        self.import_worker.moveToThread(self.import_thread)
        self.import_thread.started.connect(self.import_worker.run)
        self.import_worker.progress.connect(self.ocr_progress_update)
        self.import_worker.finished.connect(self.import_finished)
        self.import_worker.failed.connect(self.import_failed)
        self.import_worker.finished.connect(self.import_thread.quit)
        self.import_worker.failed.connect(self.import_thread.quit)
        self.import_worker.finished.connect(self.import_worker.deleteLater)
        self.import_worker.failed.connect(self.import_worker.deleteLater)
        self.import_thread.finished.connect(self.import_thread.deleteLater)
        self.import_thread.start()


    def _entity_name_from_doc_value(self, value: object, items: list[Entity]) -> str:
        if isinstance(value, dict):
            return str(value.get("name") or value.get("title") or value.get("id") or "")
        try:
            wanted = int(value)  # type: ignore[arg-type]
        except Exception:
            return str(value or "")
        for item in items:
            if item.id == wanted:
                return item.name
        return str(wanted)

    def _format_existing_paperless_document(self, result: ImportResult) -> str:
        doc = result.existing_document or {}
        if not doc:
            return "Vorhandenes Paperless-Dokument konnte nicht geladen werden."
        tags_raw = doc.get("tags") or []
        tag_names: list[str] = []
        if isinstance(tags_raw, list):
            for t in tags_raw:
                if isinstance(t, dict):
                    tag_names.append(str(t.get("name") or t.get("id") or ""))
                else:
                    tag_names.append(self._entity_name_from_doc_value(t, self.metadata.tags))
        corr = self._entity_name_from_doc_value(doc.get("correspondent"), self.metadata.correspondents)
        dtype = self._entity_name_from_doc_value(doc.get("document_type"), self.metadata.document_types)
        storage = self._entity_name_from_doc_value(doc.get("storage_path"), self.metadata.storage_paths)
        parts = [
            f"Dokument-ID: {result.document_id}",
            f"Link: {result.paperless_url or '—'}",
            f"Titel: {doc.get('title') or '—'}",
            f"created: {doc.get('created') or '—'}",
            f"added: {doc.get('added') or doc.get('created_at') or '—'}",
            f"Korrespondent: {corr or '—'}",
            f"Dokumenttyp: {dtype or '—'}",
            f"Storage Path: {storage or '—'}",
            f"Tags: {', '.join([x for x in tag_names if x]) or '—'}",
            f"Archiv-Dateiname: {doc.get('archive_filename') or '—'}",
            f"Original-Dateiname: {doc.get('original_file_name') or doc.get('original_filename') or '—'}",
        ]
        return "\n".join(parts)

    def _ask_trash_duplicate_source(self, result: ImportResult) -> None:
        if not result.duplicate_detected or not result.document_id or result.trashed:
            return
        source = Path(result.renamed_to or result.file)
        doc_text = self._format_existing_paperless_document(result)
        msg = (
            "Paperless hat die Datei als Duplikat erkannt und auf ein vorhandenes Dokument verwiesen.\n\n"
            f"{doc_text}\n\n"
            f"Lokale Quelldatei:\n{source}\n\n"
            "Soll diese lokale Datei jetzt in den Papierkorb verschoben werden?\n"
            "Paperless bleibt die Quelle der Wahrheit; bei Nein bleibt die Datei liegen."
        )
        answer = QMessageBox.question(
            self,
            "Duplikat in Paperless vorhanden",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                move_to_trash(source)
                result.trashed = True
                self.logger.info(f"Lokale Duplikatdatei in Papierkorb verschoben: {source}")
                QMessageBox.information(self, "Papierkorb", "Lokale Duplikatdatei wurde in den Papierkorb verschoben.")
            except Exception as exc:
                result.trash_error = str(exc)
                self.logger.error(f"Duplikatdatei konnte nicht in den Papierkorb verschoben werden: {exc}")
                QMessageBox.critical(self, "Papierkorb fehlgeschlagen", str(exc))
            self.log.setPlainText(self.logger.text())

    def _maybe_auto_close_after_success(self, result: ImportResult) -> None:
        if result.dry_run or not self.cfg.gui.close_after_success:
            return
        document_ok = bool(result.document_id) and (result.task_success or result.duplicate_detected) and not (result.task_failed and not result.duplicate_detected)
        # Only close when the local workflow reached a safe terminal state.
        # If Deck/backlinks blocked trash or the user still has to decide a duplicate,
        # keep the window open.
        blocked = any(
            needle in warning
            for warning in result.warnings
            for needle in (
                "nicht verschoben",
                "nicht aktualisiert",
                "nicht angelegt",
                "bitte im Duplikat-Dialog entscheiden",
            )
        )
        if document_ok and not blocked:
            delay_ms = max(0, int(self.cfg.gui.close_after_seconds)) * 1000
            self.logger.info(f"Import vollständig; Fenster schließt automatisch in {self.cfg.gui.close_after_seconds}s.")
            self.log.setPlainText(self.logger.text())
            QTimer.singleShot(delay_ms, self.close)

    def import_finished(self, result: ImportResult) -> None:
        self.import_btn.setEnabled(True)
        self.dry_btn.setEnabled(True)
        if result.dry_run:
            message = f"Dry-run ok. Rename-Ziel: {result.renamed_to or '—'}"
            title = "Dry-run"
        else:
            if result.duplicate_detected and result.document_id:
                headline = "Paperless hat die Datei als Duplikat erkannt; vorhandenes Dokument wird referenziert."
                title = "Duplikat erkannt"
            elif result.task_failed:
                headline = "Paperless hat den Import als FEHLGESCHLAGEN gemeldet."
                title = "Import nicht abgeschlossen"
            elif result.task_success and result.document_id:
                headline = "Paperless-Rückmeldung erfasst."
                title = "Import abgeschlossen"
            else:
                headline = "Paperless-Rückmeldung erfasst, aber noch nicht final."
                title = "Import unvollständig"
            parts = [
                headline,
                f"Task: {result.task_id}",
                f"Status: {result.task_status or '—'}",
                f"Task erfolgreich: {'ja' if result.task_success else 'nein'}",
                f"Task fehlgeschlagen: {'ja' if result.task_failed else 'nein'}",
                f"Dokument-ID: {result.document_id or 'noch unbekannt'}",
            ]
            if result.duplicate_detected:
                parts.append(f"Duplikat: ja, vorhandenes Dokument #{result.duplicate_document_id or result.document_id or '—'}")
                if result.duplicate_reason:
                    parts.append(f"Paperless-Hinweis: {result.duplicate_reason}")
            if result.paperless_url:
                parts.append(f"Dokument-Link: {result.paperless_url}")
            if result.global_document_id:
                parts.append(f"Globale Dokument-ID: {result.global_document_id}")
            if result.process_id:
                parts.append(f"Vorgangs-ID: {result.process_id}")
            if result.paperless_backlink_fields:
                parts.append(f"Paperless-Rücklinkfelder: {'aktualisiert' if result.paperless_backlink_updated else 'nicht aktualisiert'}")
            if result.paperless_backlink_error:
                parts.append(f"Paperless-Rücklink-Fehler: {result.paperless_backlink_error}")
            if result.sidecar_json or result.sidecar_md:
                parts.append(f"Nextcloud-Rückverweis: {result.sidecar_json or result.sidecar_md}")
            if result.deck.attempted or result.deck.created:
                parts.append(f"Deck-Karte: {result.deck.card_url or result.deck.card_id or result.deck.reason or '—'}")
                if result.deck.due_date:
                    parts.append(f"Deck fällig: {result.deck.due_date}")
                if result.deck.start_date:
                    parts.append(f"Deck Start: {result.deck.start_date}")
                if result.deck.effort:
                    parts.append(f"Deck Aufwand/Vorlauf: {result.deck.effort}")
            parts.append(f"Quelldatei im Papierkorb: {'ja' if result.trashed else 'nein'}")
            if result.trash_error:
                parts.append(f"Papierkorb-Fehler: {result.trash_error}")
            if result.warnings:
                parts.append("Warnungen:\n- " + "\n- ".join(result.warnings))
            message = "\n".join(parts)
        self.logger.info(
            f"Import result: task={result.task_id} status={result.task_status} document={result.document_id} "
            f"deck={result.deck.card_id or '-'} trashed={result.trashed} dry={result.dry_run}"
        )
        for warning in result.warnings:
            self.logger.warn(warning)
        self.log.setPlainText(self.logger.text())
        QMessageBox.information(self, title, message)
        self._ask_trash_duplicate_source(result)
        self._maybe_auto_close_after_success(result)

    def import_failed(self, message: str) -> None:
        self.import_btn.setEnabled(True)
        self.dry_btn.setEnabled(True)
        self.logger.error(message)
        self.log.setPlainText(self.logger.text())
        QMessageBox.critical(self, "Fehler", message)




    def _auto_run_ocr_if_missing_text_layer(self) -> None:
        try:
            if getattr(self, "_auto_ocr_started_once", False):
                return
            if not getattr(self, "current_info", None):
                return

            texts = []
            for widget_type in (QLabel, QLineEdit, QTextEdit):
                for widget in self.findChildren(widget_type):
                    try:
                        if hasattr(widget, "toPlainText"):
                            value = widget.toPlainText()
                        else:
                            value = widget.text()
                        if value:
                            texts.append(str(value))
                    except Exception:
                        pass

            joined = "\\n".join(texts).casefold()
            missing_text = (
                "ocr empfohlen" in joined
                or "keine ausreichende textschicht" in joined
                or "0 zeichen" in joined
            )
            if not missing_text:
                return

            self._auto_ocr_started_once = True
            QTimer.singleShot(50, lambda: self.run_ocr(False))
        except Exception as exc:
            try:
                self.logger.warning("Auto-OCR konnte nicht gestartet werden: %s", exc)
            except Exception:
                pass


def run_gui(cfg: AppConfig, logger: AppLogger, files: list[str], *, dry_run: bool, no_cache: bool) -> int:
    app = QApplication.instance() or QApplication([])
    paths = collect_input_files(files, cfg.import_.inbox_dir, cfg.import_.pattern, cfg.import_.min_age_seconds)
    if not paths:
        if files:
            detail = "\n".join(files)
            QMessageBox.warning(
                None,
                "Paperless Import",
                "Keine Eingabedateien gefunden.\n\n"
                "Die übergebenen Pfade existieren nicht als Datei/Ordner oder ein übergebener Ordner enthält keine passenden Dateien.\n\n"
                f"Übergeben:\n{detail}",
            )
        else:
            QMessageBox.warning(
                None,
                "Paperless Import",
                f"Keine Eingabedateien gefunden.\n\n"
                f"Gescannt wurde: {cfg.import_.inbox_dir}\n"
                f"Muster: {cfg.import_.pattern}\n"
                f"Mindestalter: {cfg.import_.min_age_seconds}s",
            )
        return 0
    window = MainWindow(cfg, logger, paths, dry_run=dry_run, no_cache=no_cache)
    window.show()
    return int(app.exec())
