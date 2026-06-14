from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
except Exception:  # pragma: no cover - import depends on Qt build
    QPdfDocument = None  # type: ignore[assignment]
    QPdfView = None  # type: ignore[assignment]


class PdfViewer(QWidget):
    """Embedded Qt PDF viewer with selectable extracted text panel.

    QPdfView renders the document and supports multi-page viewing, but it does
    not provide a Paperless-like mouse text-selection UX out of the box.  For
    copying, we extract the PDF text layer via QPdfDocument.getAllText() and
    show it in a read-only QTextEdit.  That text is selectable and copyable.
    Scanned documents without OCR/text layer will naturally produce little or
    no text; the external viewer button remains available.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path: Path | None = None
        self.document: Any = None
        self.view: Any = None
        self.message = QLabel("Keine PDF geladen")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)

        self.open_external_action = QAction("Extern öffnen", self)
        self.open_external_action.triggered.connect(self.open_external)
        self.toolbar.addAction(self.open_external_action)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)

        if QPdfDocument is not None and QPdfView is not None:
            self.document = QPdfDocument(self)
            self.view = QPdfView(self)
            self.view.setDocument(self.document)
            self.view.setPageMode(QPdfView.PageMode.MultiPage)
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

            all_pages = QAction("Alle Seiten", self)
            all_pages.triggered.connect(self.all_pages)
            single_page = QAction("Einzel", self)
            single_page.triggered.connect(self.single_page)
            fit_width = QAction("Breite", self)
            fit_width.triggered.connect(self.fit_width)
            fit_page = QAction("Seite", self)
            fit_page.triggered.connect(self.fit_page)
            zoom_out = QAction("−", self)
            zoom_out.triggered.connect(self.zoom_out)
            zoom_in = QAction("+", self)
            zoom_in.triggered.connect(self.zoom_in)
            zoom_100 = QAction("100 %", self)
            zoom_100.triggered.connect(lambda: self.set_zoom(1.0))

            self.text_current_action = QAction("Text Seite", self)
            self.text_current_action.setToolTip("Text der aktuellen PDF-Seite anzeigen")
            self.text_current_action.triggered.connect(self.show_current_page_text)
            self.text_all_action = QAction("Text alle", self)
            self.text_all_action.setToolTip("Text aller PDF-Seiten anzeigen")
            self.text_all_action.triggered.connect(self.show_all_text)
            self.copy_text_action = QAction("Text kopieren", self)
            self.copy_text_action.setToolTip("Gesamten Text aus dem Textbereich kopieren")
            self.copy_text_action.triggered.connect(self.copy_visible_text)
            self.hide_text_action = QAction("Text ausblenden", self)
            self.hide_text_action.triggered.connect(self.hide_text_panel)

            self.toolbar.addAction(all_pages)
            self.toolbar.addAction(single_page)
            self.toolbar.addSeparator()
            self.toolbar.addAction(fit_width)
            self.toolbar.addAction(fit_page)
            self.toolbar.addAction(zoom_out)
            self.toolbar.addAction(zoom_in)
            self.toolbar.addAction(zoom_100)
            self.toolbar.addSeparator()
            self.toolbar.addAction(self.text_current_action)
            self.toolbar.addAction(self.text_all_action)
            self.toolbar.addAction(self.copy_text_action)
            self.toolbar.addAction(self.hide_text_action)

            self.text_edit = QTextEdit(self)
            self.text_edit.setReadOnly(True)
            self.text_edit.setPlaceholderText(
                "Text aus der PDF-Textschicht. Hier kann markiert und kopiert werden. "
                "Bei reinen Scans ohne OCR bleibt dieser Bereich leer."
            )
            self.text_edit.setVisible(False)
            self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

            self.splitter = QSplitter(Qt.Orientation.Vertical)
            self.splitter.addWidget(self.view)
            self.splitter.addWidget(self.text_edit)
            self.splitter.setSizes([780, 220])
            layout.addWidget(self.splitter, 1)
        else:
            self.message.setText(
                "QtPdf ist nicht verfügbar. Bitte PySide6 mit QtPdf installieren oder extern öffnen."
            )
            layout.addWidget(self.message, 1)

    def load(self, path: Path | None) -> None:
        self.path = path
        if not path:
            self.message.setText("Keine PDF geladen")
            return
        if self.document is not None:
            self.document.load(str(path))
            if self.view is not None:
                self.fit_width()
            if hasattr(self, "text_edit"):
                self.text_edit.clear()
                self.text_edit.setVisible(False)
        else:
            self.message.setText(str(path))

    def all_pages(self) -> None:
        if self.view is not None:
            self.view.setPageMode(QPdfView.PageMode.MultiPage)
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def single_page(self) -> None:
        if self.view is not None:
            self.view.setPageMode(QPdfView.PageMode.SinglePage)
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def fit_width(self) -> None:
        if self.view is not None:
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def fit_page(self) -> None:
        if self.view is not None:
            self.view.setZoomMode(QPdfView.ZoomMode.FitInView)

    def set_zoom(self, factor: float) -> None:
        if self.view is not None:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(max(0.1, min(8.0, factor)))

    def zoom_in(self) -> None:
        if self.view is not None:
            self.set_zoom(self.view.zoomFactor() * 1.2)

    def zoom_out(self) -> None:
        if self.view is not None:
            self.set_zoom(self.view.zoomFactor() / 1.2)

    def open_external(self) -> None:
        if not self.path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def hide_text_panel(self) -> None:
        if hasattr(self, "text_edit"):
            self.text_edit.setVisible(False)

    def show_text(self, text: str) -> None:
        self._show_text(text or "[Kein Text vorhanden.]")

    def show_current_page_text(self) -> None:
        if self.document is None:
            return
        page = self._current_page()
        text = self._page_text(page)
        heading = f"--- Seite {page + 1} ---\n"
        self._show_text(heading + (text or "[Keine Textschicht auf dieser Seite gefunden.]"))

    def show_all_text(self) -> None:
        if self.document is None:
            return
        chunks: list[str] = []
        for page in range(self._page_count()):
            text = self._page_text(page)
            chunks.append(f"--- Seite {page + 1} ---\n{text}" if text else f"--- Seite {page + 1} ---\n[Keine Textschicht gefunden.]")
        body = "\n\n".join(chunks).strip()
        if not body:
            body = "Keine Textschicht gefunden. Bei gescannten Dokumenten ist OCR erforderlich."
        self._show_text(body)

    def extract_all_text(self) -> str:
        """Return all text from the loaded PDF without changing the visible UI."""
        if self.document is None:
            return ""
        chunks: list[str] = []
        for page in range(self._page_count()):
            text = self._page_text(page)
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()

    def copy_visible_text(self) -> None:
        if not hasattr(self, "text_edit"):
            return
        text = self.text_edit.textCursor().selectedText()
        if not text:
            text = self.text_edit.toPlainText()
        QApplication.clipboard().setText(text)
        if text:
            QMessageBox.information(self, "Text kopiert", "Text wurde in die Zwischenablage kopiert.")

    def _show_text(self, text: str) -> None:
        if not hasattr(self, "text_edit"):
            return
        self.text_edit.setPlainText(text)
        self.text_edit.setVisible(True)
        self.text_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self.text_edit.moveCursor(self.text_edit.textCursor().Start)
        if hasattr(self, "splitter"):
            self.splitter.setSizes([650, 280])

    def _current_page(self) -> int:
        if self.view is None:
            return 0
        try:
            nav = self.view.pageNavigator()
            page = nav.currentPage()
            if isinstance(page, int) and page >= 0:
                return page
        except Exception:
            pass
        return 0

    def _page_count(self) -> int:
        if self.document is None:
            return 0
        try:
            return max(0, int(self.document.pageCount()))
        except Exception:
            return 0

    def _page_text(self, page: int) -> str:
        if self.document is None or page < 0:
            return ""
        try:
            selection = self.document.getAllText(page)
        except Exception:
            return ""
        return self._selection_text(selection).strip()

    @staticmethod
    def _selection_text(selection: Any) -> str:
        if selection is None:
            return ""
        valid_attr = getattr(selection, "isValid", None)
        try:
            if callable(valid_attr) and not valid_attr():
                return ""
        except Exception:
            pass
        valid_prop = getattr(selection, "valid", None)
        try:
            if callable(valid_prop) and not valid_prop():
                return ""
            if isinstance(valid_prop, bool) and not valid_prop:
                return ""
        except Exception:
            pass
        text_attr = getattr(selection, "text", None)
        try:
            if callable(text_attr):
                return str(text_attr())
            if text_attr is not None:
                return str(text_attr)
        except Exception:
            return ""
        return ""
