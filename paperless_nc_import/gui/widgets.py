from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPixmap, QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..deadline import DeadlineMode, GERMAN_STATE_LABELS, calculate_deadline
from ..models import CustomField, Entity
from ..validators import is_valid_iban, normalize_iban, parse_bool, parse_number


class SubmitLineEdit(QLineEdit):
    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class EntityPicker(QWidget):
    changed = Signal(object)

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entities: list[Entity] = []
        self.filtered: list[Entity] = []
        self.selected: Entity | None = None
        self.title = QLabel(label)
        self.search = SubmitLineEdit()
        self.search.setPlaceholderText(f"{label} suchen; Enter übernimmt ersten Treffer")
        self.selected_label = QLabel("Ausgewählt: —")
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.clear_button = QPushButton("Leeren")
        self.take_first_button = QPushButton("1. Treffer übernehmen")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.take_first_button)
        top.addWidget(self.clear_button)
        layout.addWidget(self.title)
        layout.addLayout(top)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.list)

        self.search.textChanged.connect(self.refilter)
        self.search.submitted.connect(self.select_first)
        self.take_first_button.clicked.connect(self.select_first)
        self.clear_button.clicked.connect(self.clear)
        self.list.itemActivated.connect(self._activate_item)
        self.list.itemClicked.connect(self._activate_item)

    def set_entities(self, values: list[Entity]) -> None:
        self.entities = list(values)
        self.refilter()

    def refilter(self) -> None:
        needle = self.search.text().strip().casefold()
        if needle:
            self.filtered = [x for x in self.entities if needle in x.name.casefold()]
        else:
            self.filtered = self.entities[:100]
        self.list.clear()
        for entity in self.filtered[:200]:
            item = QListWidgetItem(entity.name)
            item.setData(Qt.ItemDataRole.UserRole, entity)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _activate_item(self, item: QListWidgetItem) -> None:
        entity = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entity, Entity):
            self.selected = entity
            self.selected_label.setText(f"Ausgewählt: {entity.name}")
            self.changed.emit(entity)

    def select_first(self) -> None:
        if self.list.count():
            self._activate_item(self.list.item(0))

    def clear(self) -> None:
        self.selected = None
        self.search.clear()
        self.selected_label.setText("Ausgewählt: —")
        self.changed.emit(None)


def _color_icon(value: str) -> QIcon:
    color = QColor(value)
    if not color.isValid():
        color = QColor("#999999")
    pix = QPixmap(16, 16)
    pix.fill(color)
    return QIcon(pix)

class TagSelector(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tags: list[Entity] = []
        self.default_selected: set[int] = set()
        self.extra_tags: list[str] = []
        self.selected_ids: set[int] = set()
        self.selected_label = QLabel("Ausgewählte Tags: —")
        self.selected_label.setWordWrap(True)
        self.selected_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.selected_label.setStyleSheet("padding: 4px; background: #f7f7f7; border: 1px solid #ddd;")
        self.search = SubmitLineEdit()
        self.search.setPlaceholderText("Tags suchen; Enter wählt ersten Treffer")
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.list.setMaximumHeight(230)
        self.extra_entry = SubmitLineEdit()
        self.extra_entry.setPlaceholderText("Neue/zusätzliche Tags; Komma oder Semikolon für mehrere")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        layout.addWidget(QLabel("Neue Tags werden beim Import übernommen; Enter fügt sie sofort hinzu."))
        layout.addWidget(self.extra_entry)

        self.search.textChanged.connect(self.refilter)
        self.search.submitted.connect(self.toggle_first)
        self.list.itemChanged.connect(self._item_changed)
        self.list.itemActivated.connect(lambda item: self._toggle_item(item))
        self.extra_entry.submitted.connect(self.add_extra)

    def set_tags(self, tags: list[Entity], selected: list[Entity] | None = None) -> None:
        self.tags = list(tags)
        self.default_selected = {t.id for t in selected or []}
        self.selected_ids = set(self.default_selected)
        self.refilter()
        self.update_label()

    def refilter(self) -> None:
        needle = self.search.text().strip().casefold()
        values = [x for x in self.tags if not needle or needle in x.name.casefold()]
        # Selected tags stay visible at top, but text remains readable.  Paperless
        # colours are shown as small icons instead of colouring the full row.
        values.sort(key=lambda x: (0 if x.id in self.selected_ids else 1, x.name.casefold()))
        self.list.blockSignals(True)
        self.list.clear()
        for tag in values[:300]:
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if tag.id in self.selected_ids else Qt.CheckState.Unchecked)
            if tag.color:
                item.setIcon(_color_icon(tag.color))
                item.setToolTip(f"{tag.name} — Paperless-Farbe {tag.color}")
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.update_label()

    def _item_changed(self, item: QListWidgetItem) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(tag, Entity):
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_ids.add(tag.id)
            else:
                self.selected_ids.discard(tag.id)
        self.update_label()

    def _toggle_item(self, item: QListWidgetItem) -> None:
        item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def toggle_first(self) -> None:
        if self.list.count():
            self._toggle_item(self.list.item(0))

    def selected_tags(self) -> list[Entity]:
        ids = set(self.selected_ids)
        return [tag for tag in self.tags if tag.id in ids]

    def add_extra(self) -> None:
        raw = self.extra_entry.text().replace(";", ",")
        for part in raw.split(","):
            value = part.strip()
            if value and value not in self.extra_tags:
                self.extra_tags.append(value)
        self.extra_entry.clear()
        self.update_label()

    def update_label(self) -> None:
        names = [t.name for t in self.selected_tags()] + self.extra_tags
        self.selected_label.setText("Ausgewählte Tags: " + (", ".join(names) if names else "—"))
        self.changed.emit()


class DateDeadlineWidget(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, allow_bgb: bool = True) -> None:
        super().__init__(parent)
        self.allow_bgb = allow_bgb
        self.base_dates: dict[str, date] = {"heute": date.today()}
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(lambda _: self.changed.emit())
        self.amount = QSpinBox()
        self.amount.setRange(1, 9999)
        self.amount.setValue(1)
        self.unit = QComboBox()
        self.unit.addItems(["Tage", "Wochen", "Monate", "Jahre"])
        self.base = QComboBox()
        self.base.addItems(["ab heute"])
        self.mode = QComboBox()
        self.mode.addItem("Wiedervorlage / kalendarisch", DeadlineMode.REMINDER.value)
        if allow_bgb:
            self.mode.addItem("BGB Ereignisfrist (§187 I)", DeadlineMode.BGB_EVENT.value)
            self.mode.addItem("BGB Beginnfrist (§187 II)", DeadlineMode.BGB_START.value)
        self.apply_193 = QCheckBox("§193 BGB Sa/So/Feiertag")
        self.apply_193.setChecked(False)
        self.apply_193.setEnabled(allow_bgb)
        self.holiday_state = QComboBox()
        for code, label in GERMAN_STATE_LABELS:
            self.holiday_state.addItem(label, code)
        # Frank arbeitet regelmäßig Berlin/Brandenburg; Berlin ist ein brauchbarer Default,
        # bleibt aber bewusst sichtbar änderbar, weil §193 vom Ort abhängen kann.
        idx = self.holiday_state.findData("BE")
        if idx >= 0:
            self.holiday_state.setCurrentIndex(idx)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_custom = QPushButton("Frist setzen")
        self.set_custom.clicked.connect(self.apply_custom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(self.date_edit, 1)
        quicks: list[tuple[str, int, str]] = [
            ("Heute", 0, "Tage"),
            ("+1 Woche", 1, "Wochen"),
            ("+2 Wochen", 2, "Wochen"),
            ("+1 Monat", 1, "Monate"),
            ("+3 Monate", 3, "Monate"),
        ]
        for label, amount, unit in quicks:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, a=amount, u=unit: self.apply_quick(a, u))
            top.addWidget(btn)
        layout.addLayout(top)

        if allow_bgb:
            mode_row = QHBoxLayout()
            mode_row.addWidget(QLabel("Berechnung"))
            mode_row.addWidget(self.mode, 1)
            mode_row.addWidget(self.apply_193)
            mode_row.addWidget(self.holiday_state)
            layout.addLayout(mode_row)
        else:
            self.mode.setVisible(False)
            self.apply_193.setVisible(False)
            self.holiday_state.setVisible(False)

        bottom = QHBoxLayout()
        bottom.addWidget(self.amount)
        bottom.addWidget(self.unit)
        bottom.addWidget(self.base)
        bottom.addStretch(1)
        bottom.addWidget(self.set_custom)
        layout.addLayout(bottom)
        layout.addWidget(self.note)

        self.mode.currentIndexChanged.connect(lambda _: self._update_mode_hint())
        self.apply_193.toggled.connect(lambda _: self._update_mode_hint())
        self.holiday_state.currentIndexChanged.connect(lambda _: self._update_mode_hint())
        self._update_mode_hint()

    def set_base_dates(self, values: dict[str, date]) -> None:
        self.base_dates = {"heute": date.today(), **values}
        self.base.clear()
        for key in self.base_dates:
            self.base.addItem(f"ab {key}", key)

    def set_date(self, value: date) -> None:
        self.date_edit.setDate(QDate(value.year, value.month, value.day))

    def get_date(self) -> date:
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def _current_mode(self) -> DeadlineMode:
        try:
            return DeadlineMode(str(self.mode.currentData() or DeadlineMode.REMINDER.value))
        except ValueError:
            return DeadlineMode.REMINDER

    def _holiday_state_code(self) -> str:
        return str(self.holiday_state.currentData() or "")

    def _update_mode_hint(self) -> None:
        if not self.allow_bgb:
            self.note.setText("Kalenderdatum; keine Fristberechnung.")
            return
        mode = self._current_mode()
        if mode == DeadlineMode.REMINDER:
            self.apply_193.setEnabled(False)
            self.holiday_state.setEnabled(False)
            self.note.setText("Wiedervorlage: Monate/Jahre werden kalendarisch berechnet; keine §193-Verschiebung.")
        else:
            self.apply_193.setEnabled(True)
            self.holiday_state.setEnabled(self.apply_193.isChecked())
            if mode == DeadlineMode.BGB_EVENT:
                self.note.setText("BGB Ereignisfrist: Ereignistag zählt nicht mit (§187 I); Ende nach §188; optional §193.")
            else:
                self.note.setText("BGB Beginnfrist: Anfangstag zählt mit (§187 II); Ende nach §188 am Vortag; optional §193.")

    def apply_quick(self, amount: int, unit: str) -> None:
        if amount == 0 and unit == "Tage":
            self.set_date(date.today())
            self.note.setText("Heute gesetzt.")
            self.changed.emit()
            return
        key = self.base.currentData() or "heute"
        base = self.base_dates.get(str(key), date.today())
        result = calculate_deadline(
            base,
            amount,
            unit,
            mode=self._current_mode(),
            apply_193=self.allow_bgb and self.apply_193.isChecked(),
            holiday_state=self._holiday_state_code(),
        )
        self.set_date(result.value)
        self.note.setText(result.note)
        self.changed.emit()

    def apply_custom(self) -> None:
        key = self.base.currentData() or "heute"
        base = self.base_dates.get(str(key), date.today())
        result = calculate_deadline(
            base,
            self.amount.value(),
            self.unit.currentText(),
            mode=self._current_mode(),
            apply_193=self.allow_bgb and self.apply_193.isChecked(),
            holiday_state=self._holiday_state_code(),
        )
        self.set_date(result.value)
        self.note.setText(result.note)
        self.changed.emit()


class CustomFieldEditor(QWidget):
    changed = Signal()

    def __init__(self, correspondents: list[Entity], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.field: CustomField | None = None
        self.correspondents = correspondents
        self.sources: dict[str, Callable[[], Any]] = {}
        self.current_value: Any = None

        self.label = QLabel("Kein Custom Field ausgewählt")
        self.source = QComboBox()
        self.source.currentIndexChanged.connect(self.update_source)
        self.text = SubmitLineEdit()
        self.text.textChanged.connect(self._manual_changed)
        self.bool_value = QCheckBox("wahr / gesetzt")
        self.bool_value.toggled.connect(lambda _: self.changed.emit())
        self.date_value = DateDeadlineWidget()
        self.date_value.changed.connect(lambda: self.changed.emit())
        self.iban_status = QLabel("")

        self.take = QPushButton("Custom Field übernehmen")
        self.remove = QPushButton("Auswahl entfernen")

        self.form_layout = QFormLayout(self)
        self.form_layout.addRow("Feld", self.label)
        self.form_layout.addRow("Wertquelle", self.source)
        self.form_layout.addRow("Wert", self.text)
        self.form_layout.addRow("Wert", self.bool_value)
        self.form_layout.addRow("Datum", self.date_value)
        self.form_layout.addRow("Prüfung", self.iban_status)
        buttons = QHBoxLayout()
        buttons.addWidget(self.take)
        buttons.addWidget(self.remove)
        buttons.addStretch(1)
        self.form_layout.addRow(buttons)
        self._show_by_type(None)

        self.extraction_debug_label = QLabel("")
        self.extraction_debug_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.extraction_debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.extraction_debug_label.setWordWrap(True)
        try:
            self.grid.attach(self.extraction_debug_label, 1, 3, 2, 1)
        except Exception:
            try:
                self.pack_start(self.extraction_debug_label, False, False, 0)
            except Exception:
                pass

    def set_context(self, sources: dict[str, Callable[[], Any]], base_dates: dict[str, date]) -> None:
        self.sources = sources
        self.date_value.set_base_dates(base_dates)
        self._populate_sources()


    def set_extraction_debug(self, text: str) -> None:
        if hasattr(self, "extraction_debug_label"):
            self.extraction_debug_label.setText(text or "")

    def set_field(
        self,
        field: CustomField | None,
        suggestions: list[str] | None = None,
        prefill_value: Any | None = None,
    ) -> None:
        self.field = field
        self.text.setReadOnly(False)
        self.text.setCompleter(None)
        if not field:
            self.label.setText("Kein Custom Field ausgewählt")
            self._show_by_type(None)
            return
        self.label.setText(f"{field.name} [#{field.id}, {field.normalized_type}]")
        self._populate_sources()
        self._show_by_type(field)
        self.text.clear()

        merged_suggestions = list(suggestions or [])
        if self._is_recipient_field(field):
            # Empfänger ist ein eigenes Feld, aber vorhandene Korrespondenten sind die
            # naheliegenden Vorschläge beim Tippen. Es wird nichts automatisch gleichgesetzt.
            merged_suggestions.extend(c.name for c in self.correspondents)
        # Stable, duplicate-free order.
        seen: set[str] = set()
        merged_suggestions = [x for x in merged_suggestions if x and not (x in seen or seen.add(x))]
        if merged_suggestions:
            from PySide6.QtWidgets import QCompleter
            completer = QCompleter(merged_suggestions, self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.text.setCompleter(completer)

        if prefill_value not in (None, ""):
            if field.normalized_type == "boolean":
                self.bool_value.setChecked(parse_bool(prefill_value))
            elif field.normalized_type == "date":
                try:
                    value = date.fromisoformat(str(prefill_value)[:10])
                    self.date_value.set_date(value)
                except Exception:
                    pass
            else:
                self.text.setText(str(prefill_value))

    @staticmethod
    def _is_recipient_field(field: CustomField) -> bool:
        name = field.name.casefold()
        return any(token in name for token in ["empfänger", "empfaenger", "recipient", "adressat"])

    @staticmethod
    def _has_any(name: str, tokens: list[str]) -> bool:
        return any(token in name for token in tokens)

    def _populate_sources(self) -> None:
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItem("Manueller Wert", "manual")
        if self.field:
            name = self.field.name.casefold()
            typ = self.field.normalized_type

            # Context-sensitive source list. Generic text fields such as Steuerart or
            # IBAN should not offer Nextcloud sources; that produced long, meaningless
            # menus. Only names that actually ask for provenance/link/hash/title get
            # those sources.
            if self._is_recipient_field(self.field):
                self.source.addItem("Empfänger: aus gewähltem Korrespondent", "recipient_from_correspondent")

            if typ == "date":
                for key in ["document_date", "birthtime_date", "today"]:
                    if key in self.sources:
                        self.source.addItem(self._source_label(key), key)
            elif typ in {"string", "url"}:
                keys: list[str] = []
                if self._has_any(name, ["nextcloud", "arbeitsordner", "cloud", "web-link", "weblink", "web link"]):
                    keys.extend(["nextcloud_internal", "nextcloud_web", "nextcloud_cloud", "nextcloud_webdav"])
                if self._has_any(name, ["webdav"]):
                    keys.append("nextcloud_webdav")
                if self._has_any(name, ["fileid", "file-id", "ocid"]):
                    keys.append("nextcloud_internal")
                if self._has_any(name, ["pfad", "path", "lokal", "local"]):
                    keys.extend(["nextcloud_cloud", "local_path"])
                if self._has_any(name, ["sha", "hash", "prüfsumme", "pruefsumme"]):
                    keys.append("sha256")
                if self._has_any(name, ["titel", "title"]):
                    keys.append("title")
                # Preserve order and avoid duplicates.
                seen_keys: set[str] = set()
                for key in keys:
                    if key in self.sources and key not in seen_keys:
                        seen_keys.add(key)
                        self.source.addItem(self._source_label(key), key)
        self.source.blockSignals(False)
        self.source.setCurrentIndex(0)
        self.text.setReadOnly(False)

    @staticmethod
    def _source_label(key: str) -> str:
        labels = {
            "nextcloud_internal": "Nextcloud interner Link (/f/FileID)",
            "nextcloud_web": "Nextcloud Web-Link",
            "nextcloud_cloud": "Nextcloud Cloud-Pfad",
            "nextcloud_webdav": "Nextcloud WebDAV-URL",
            "local_path": "Lokaler Pfad",
            "sha256": "SHA256",
            "title": "Titel",
            "document_date": "Dokumentdatum",
            "birthtime_date": "Birthtime",
            "today": "Heute",
        }
        return labels.get(key, key)

    def _row_visible(self, widget: QWidget, visible: bool) -> None:
        label = self.form_layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
        widget.setVisible(visible)

    def _show_by_type(self, field: CustomField | None) -> None:
        typ = field.normalized_type if field else "string"
        self._row_visible(self.source, typ != "boolean")
        self._row_visible(self.bool_value, typ == "boolean")
        self._row_visible(self.date_value, typ == "date")
        self._row_visible(self.text, typ not in {"boolean", "date"})
        self._row_visible(self.iban_status, bool(field and "iban" in field.name.casefold()))
        if typ == "integer":
            self.text.setValidator(QRegularExpressionValidator(QRegularExpression(r"[-+]?[0-9]+"), self.text))
        elif typ in {"float", "monetary"}:
            self.text.setValidator(QRegularExpressionValidator(QRegularExpression(r"[-+]?[0-9.,]+"), self.text))
        else:
            self.text.setValidator(None)

    def update_source(self) -> None:
        if not self.field:
            return
        key = self.source.currentData()
        if key == "manual" or not key:
            self.text.setReadOnly(False)
            return
        if key == "recipient_from_correspondent":
            value = self.sources.get("correspondent_name", lambda: "")()
        else:
            value = self.sources.get(str(key), lambda: "")()
        if self.field.normalized_type == "date":
            if isinstance(value, datetime):
                self.date_value.set_date(value.date())
        else:
            self.text.setText(str(value or ""))
            self.text.setReadOnly(True)
        self.changed.emit()

    def _manual_changed(self) -> None:
        if self.field and "iban" in self.field.name.casefold():
            value = normalize_iban(self.text.text())
            if not value:
                self.iban_status.setText("")
            elif is_valid_iban(value):
                self.iban_status.setText("IBAN gültig")
            else:
                self.iban_status.setText("IBAN ungültig")
        self.changed.emit()

    def value(self) -> Any:
        if not self.field:
            return None
        typ = self.field.normalized_type
        if typ == "boolean":
            return bool(self.bool_value.isChecked())
        if typ == "date":
            return self.date_value.get_date().isoformat()
        text = self.text.text().strip()
        if typ == "integer":
            return parse_number(text, integer=True)
        if typ in {"float", "monetary"}:
            return parse_number(text)
        if "iban" in self.field.name.casefold():
            return normalize_iban(text)
        return text
