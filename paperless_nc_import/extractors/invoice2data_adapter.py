from __future__ import annotations

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import normalize_date, normalize_money


class Invoice2DataExtractor(BaseExtractor):
    """Optional invoice2data adapter.

    invoice2data is template-based and useful for recurring suppliers. It is not
    required for the core GUI path; when unavailable or no template matches, this
    adapter simply returns no candidates.
    """

    name = "invoice2data"
    priority = 20

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        path = item.path
        if not path or not path.exists():
            return []
        try:  # pragma: no cover - optional dependency branch
            from invoice2data import extract_data  # type: ignore
        except Exception:
            return []
        try:  # pragma: no cover - optional dependency branch
            data = extract_data(str(path)) or {}
        except Exception:
            return []
        role = (item.role or "").casefold()
        raw = ""
        value = ""
        label = "invoice2data"
        if role == "amount.total":
            raw = str(data.get("amount") or data.get("total") or "")
            value = normalize_money(raw)
            label = "invoice2data amount"
        elif role == "date.invoice":
            raw = str(data.get("date") or "")
            value = normalize_date(raw)
            label = "invoice2data date"
        elif role == "date.due":
            raw = str(data.get("due_date") or data.get("date_due") or "")
            value = normalize_date(raw)
            label = "invoice2data due date"
        if not value:
            return []
        return [
            ExtractorResult(
                role=role,
                field_type=item.field_type,
                value=value,
                raw_value=raw,
                label_normalized=label,
                extractor="invoice2data_template",
                backend=self.name,
                confidence=0.92,
            )
        ]
