from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import normalize_date, normalize_label
from .paddleocr_layout_amount import (
    LayoutRecord,
    LayoutRow,
    build_rows,
    _load_or_run_paddle_records,
    _load_paddle_config,
    _source_path,
)

DATE_PATTERN = re.compile(
    r"(?<!\d)("
    r"\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{2,4}"
    r"|"
    r"\d{4}\s*-\s*\d{1,2}\s*-\s*\d{1,2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?Z?)?"
    r")(?!\d)"
)

INVOICE_DATE_LABELS = {
    "datum",
    "belegdatum",
    "rechnungsdatum",
    "rechnung vom",
    "rechnung",
    "vom",
    "kaufdatum",
    "verkaufsdatum",
    "verkauf",
    "lieferdatum",
    "leistungsdatum",
    "bon datum",
    "kassenbon",
}
DUE_DATE_LABELS = {
    "faellig",
    "fällig",
    "faellig am",
    "fällig am",
    "zahlbar bis",
    "zahlungsziel",
    "zahlungsfrist",
    "bis zum",
    "due",
    "due date",
    "payable until",
}
PAYMENT_CONTEXT_LABELS = {
    "bezahlung",
    "zahlung erfolgt",
    "kartenzahlung",
    "kreditkarte",
    "bar",
    "visa",
    "kundenbeleg",
    "ec beleg",
}
REJECT_CONTEXT_LABELS = {
    "start",
    "ende",
    "tse",
    "transaktion",
    "transaktionsnummer",
    "signatur",
    "signaturzaehler",
    "signaturzahler",
    "terminal",
    "tid",
    "t id",
    "beleg nr",
    "bon nr",
}
TAX_CONTEXT_LABELS = {
    "mwst",
    "ust",
    "steuer",
    "netto",
    "brutto",
    "ust id",
    "ust-id",
}


@dataclass(slots=True, frozen=True)
class LayoutDate:
    value: str
    raw: str
    row_index: int
    row: LayoutRow


class PaddleOCRLayoutDateExtractor(BaseExtractor):
    """Geometry/context date extractor for OCR scans.

    This extractor is deliberately layout- and role-based, not vendor-based.
    It handles:
    - explicit labels: Datum, Rechnungsdatum, Rechnung ... vom
    - due labels: Fällig am, zahlbar bis, Zahlungsziel
    - receipt/payment blocks where a payment date is the best available receipt date
    - rejection of TSE/signature/start/end technical timestamps unless strongly labeled
    """

    name = "paddleocr_layout_date"
    priority = 43

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        role = (item.role or "").casefold()
        if role not in {"date.invoice", "date.receipt", "date.document", "date.due", "date.service"}:
            return []
        if not (item.field_type or "").casefold().startswith("date"):
            return []

        source_path = _source_path(item.sources or {})
        if not source_path:
            return []

        pdf = Path(source_path).expanduser()
        if not pdf.exists():
            return []

        cfg = _load_paddle_config(item.sources or {})
        if not cfg.get("enabled"):
            return []

        records = _load_or_run_paddle_records(pdf, cfg)
        if not records:
            return []

        rows = build_rows(records)
        candidates = list(iter_date_candidates(rows))
        if not candidates:
            return []

        scored: list[tuple[float, LayoutDate, str, str]] = []
        for candidate in candidates:
            score, label, explanation = score_date_candidate(candidate, rows, role)
            if score >= 0.62:
                scored.append((score, candidate, label, explanation))

        scored.sort(key=lambda row: row[0], reverse=True)

        out: list[ExtractorResult] = []
        for score, candidate, label, explanation in scored[:5]:
            out.append(
                ExtractorResult(
                    role=role,
                    field_type=item.field_type,
                    value=candidate.value,
                    raw_value=candidate.raw,
                    label_normalized=label,
                    extractor="paddleocr_layout_date",
                    backend="paddleocr_sidecar",
                    confidence=min(0.99, round(score, 3)),
                    explanation=explanation,
                )
            )
        return out


def iter_date_candidates(rows: list[LayoutRow]) -> list[LayoutDate]:
    found: list[LayoutDate] = []

    for idx, row in enumerate(rows):
        text = _clean_date_text(row.text)
        for match in DATE_PATTERN.finditer(text):
            raw = match.group(1)
            value = normalize_date(raw)
            if not value:
                continue
            found.append(LayoutDate(value=value, raw=raw, row_index=idx, row=row))

    return found


def score_date_candidate(candidate: LayoutDate, rows: list[LayoutRow], role: str) -> tuple[float, str, str]:
    row_norm = candidate.row.normalized
    context_rows = _row_window(rows, candidate.row_index, radius=3)
    context_norm = " ".join(row.normalized for row in context_rows)

    row_invoice_label = _contains_any(row_norm, INVOICE_DATE_LABELS)
    context_invoice_label = _contains_any(context_norm, INVOICE_DATE_LABELS)
    row_due_label = _contains_any(row_norm, DUE_DATE_LABELS)
    context_due_label = _contains_any(context_norm, DUE_DATE_LABELS)
    row_payment_label = _contains_any(row_norm, PAYMENT_CONTEXT_LABELS)
    context_payment_label = _contains_any(context_norm, PAYMENT_CONTEXT_LABELS)
    row_reject_label = _contains_any(row_norm, REJECT_CONTEXT_LABELS)
    context_reject_label = _contains_any(context_norm, REJECT_CONTEXT_LABELS)
    row_tax_label = _contains_any(row_norm, TAX_CONTEXT_LABELS)

    invoice_label = row_invoice_label or context_invoice_label
    due_label = row_due_label or context_due_label
    payment_label = row_payment_label or context_payment_label
    reject_label = row_reject_label or context_reject_label

    score = 0.10
    reasons: list[str] = []

    if role == "date.due":
        if not due_label:
            return 0.0, "", "reject due date without due label"

        if row_due_label:
            score += 0.88
            reasons.append(f"row_due_label={row_due_label}")
        else:
            score += 0.48
            reasons.append(f"context_due_label={context_due_label}")

        # A row that explicitly says Rechnungsdatum/Datum is very likely not due date,
        # even if a nearby row contains "Fällig am".
        if row_invoice_label and not row_due_label:
            score -= 0.50
            reasons.append(f"row_invoice_context_penalty={row_invoice_label}")
        elif context_invoice_label and not row_due_label:
            score -= 0.12
            reasons.append(f"context_invoice_penalty={context_invoice_label}")

    elif role in {"date.invoice", "date.receipt", "date.document", "date.service"}:
        # A row explicitly marked as due date is not an invoice/receipt date.
        if row_due_label and not row_invoice_label:
            return 0.0, row_due_label, "reject due row for invoice date role"

        if row_invoice_label:
            score += 0.78
            reasons.append(f"row_invoice_label={row_invoice_label}")
        elif context_invoice_label:
            score += 0.48
            reasons.append(f"context_invoice_label={context_invoice_label}")

        # Receipt/payment block may contain the only reliable receipt date.
        if row_payment_label:
            score += 0.30
            reasons.append(f"row_payment_context={row_payment_label}")
        elif context_payment_label:
            score += 0.18
            reasons.append(f"context_payment_context={context_payment_label}")

        if role == "date.service" and "leistungsdatum" in context_norm:
            score += 0.22
            reasons.append("service_date_label")

        if reject_label and not invoice_label and not payment_label:
            return 0.0, reject_label, "reject technical timestamp context"

        if not (invoice_label or payment_label):
            # Safe fallback only for top-of-page clearly date-like records; otherwise
            # no suggestion is better than a wrong date.
            page_rows = [r for r in rows if r.page == candidate.row.page]
            if page_rows:
                pos = page_rows.index(candidate.row) / max(1, len(page_rows) - 1)
                if pos <= 0.18:
                    score += 0.30
                    reasons.append("top_section_fallback")
                else:
                    return 0.0, "", "reject unlabeled date outside header/payment context"

    if row_reject_label and not (row_invoice_label or row_due_label or row_payment_label):
        score -= 0.35
        reasons.append(f"row_technical_context_penalty={row_reject_label}")
    elif context_reject_label and not (row_invoice_label or row_due_label or row_payment_label):
        score -= 0.16
        reasons.append(f"context_technical_context_penalty={context_reject_label}")

    if row_tax_label:
        score -= 0.15
        reasons.append(f"tax_context_penalty={row_tax_label}")

    # Same-row label is stronger than context label.
    if DATE_PATTERN.search(candidate.row.text):
        if role == "date.due" and row_due_label:
            score += 0.10
            reasons.append("same_row_due_label_date")
        elif role != "date.due" and row_invoice_label:
            score += 0.10
            reasons.append("same_row_invoice_label_date")
        elif row_payment_label:
            score += 0.06
            reasons.append("same_row_payment_date")

    if role == "date.due":
        label = row_due_label or context_due_label
    else:
        label = row_invoice_label or context_invoice_label or row_payment_label or context_payment_label
    return max(0.0, score), label, "; ".join(reasons)


def _row_window(rows: list[LayoutRow], idx: int, radius: int) -> list[LayoutRow]:
    return rows[max(0, idx - radius) : min(len(rows), idx + radius + 1)]


def _contains_any(norm: str, labels: set[str]) -> str:
    norm = normalize_label(norm)
    for label in sorted(labels, key=len, reverse=True):
        if normalize_label(label) in norm:
            return normalize_label(label)
    return ""


def _clean_date_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("−", "-")
    text = re.sub(r"(\d)\s*([.\-/])\s*(\d)", r"\1\2\3", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
