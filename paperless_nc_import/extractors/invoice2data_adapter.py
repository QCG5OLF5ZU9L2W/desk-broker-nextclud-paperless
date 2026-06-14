from __future__ import annotations

import inspect
import logging
import os
from pathlib import Path
from typing import Any

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import normalize_date, normalize_money


class Invoice2DataExtractor(BaseExtractor):
    name = "invoice2data"
    priority = 20

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        path = item.path
        if not path or not path.exists():
            return []

        try:
            from invoice2data import extract_data  # type: ignore
        except Exception:
            return []

        template_sets = self._template_sets()
        readers = self._readers()

        for templates, template_label in template_sets:
            for reader in readers:
                data = self._extract_safely(extract_data, path, templates=templates, reader=reader)
                result = self._to_result(data, item, reader=reader, template_label=template_label)
                if result:
                    return [result]

        return []

    def _readers(self) -> list[str | None]:
        raw = os.environ.get("PAPERLESS_NC_IMPORT_INVOICE2DATA_READERS")
        if raw:
            readers = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            readers = ["pdftotext", "pdfplumber", "pdfminer", "ocrmypdf", "tesseract"]
        return [None] + readers

    def _template_sets(self) -> list[tuple[Any, str]]:
        sets: list[tuple[Any, str]] = [(None, "builtins")]

        folders: list[Path] = []
        project = Path(__file__).resolve().parents[1] / "rulesets" / "invoice2data"
        if project.exists():
            folders.append(project)

        env = os.environ.get("PAPERLESS_NC_IMPORT_INVOICE2DATA_TEMPLATE_DIRS", "")
        for part in env.split(":"):
            if part.strip():
                folders.append(Path(part).expanduser())

        try:
            from invoice2data.extract.loader import read_templates  # type: ignore
        except Exception:
            return sets

        for folder in folders:
            if not folder.exists():
                continue
            try:
                templates = read_templates(str(folder))
            except Exception:
                continue
            if templates:
                sets.insert(0, (templates, str(folder)))

        return sets

    def _extract_safely(self, extract_data, path: Path, *, templates: Any, reader: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        try:
            sig = inspect.signature(extract_data)
        except Exception:
            sig = None

        if templates is not None:
            kwargs["templates"] = templates

        if reader and sig is not None:
            params = sig.parameters
            if "input_module" in params:
                kwargs["input_module"] = reader
            elif "input_reader" in params:
                kwargs["input_reader"] = reader
            elif "input_reader_name" in params:
                kwargs["input_reader_name"] = reader

        old_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.CRITICAL)
        try:
            data = extract_data(str(path), **kwargs) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
        finally:
            logging.getLogger().setLevel(old_level)

    def _to_result(
        self,
        data: dict[str, Any],
        item: ExtractorInput,
        *,
        reader: str | None,
        template_label: str,
    ) -> ExtractorResult | None:
        if not data:
            return None

        role = (item.role or "").casefold()
        raw = ""
        value = ""

        if role == "amount.total":
            raw = str(data.get("amount") or data.get("total") or data.get("amount_total") or "")
            value = normalize_money(raw)
            label = "invoice2data amount"
        elif role == "amount.vat":
            raw = str(data.get("amount_tax") or data.get("tax") or data.get("vat") or "")
            value = normalize_money(raw)
            label = "invoice2data vat"
        elif role == "date.invoice":
            raw = str(data.get("date") or data.get("invoice_date") or "")
            value = normalize_date(raw)
            label = "invoice2data date"
        elif role == "date.due":
            raw = str(data.get("due_date") or data.get("date_due") or "")
            value = normalize_date(raw)
            label = "invoice2data due date"
        else:
            return None

        if not value:
            return None

        return ExtractorResult(
            role=role,
            field_type=item.field_type,
            value=value,
            raw_value=raw,
            label_normalized=label,
            extractor=f"invoice2data_template:{reader or 'default'}",
            backend=self.name,
            confidence=0.92,
            explanation=f"template_set={template_label}; input_reader={reader or 'default'}",
        )
