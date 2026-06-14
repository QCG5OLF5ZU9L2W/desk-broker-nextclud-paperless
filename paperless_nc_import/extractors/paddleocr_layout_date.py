from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import normalize_label
from .paddleocr_layout_amount import (
    LayoutRow,
    _load_or_run_paddle_records,
    _load_paddle_config,
    _source_path,
    build_rows,
)

# ISO first, then German/common OCR date variants.
DATE_PATTERN = re.compile(
    r"(?<!\d)("
    r"(?:19|20)\d{2}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}"
    r"(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?Z?)?"
    r"|"
    r"\d{1,2}\s*[.,;/\-]\s*\d{1,2}\s*[.,;/\-]\s*\d{2,4}"
    r")(?!\d)"
)

INVOICE_DATE_LABELS = {
    "datum",
    "belegdatum",
    "bon datum",
    "kassenbon datum",
    "rechnungsdatum",
    "rechnung vom",
    "rechnung",
    "vom",
    "verkauf",
    "verkaufsdatum",
    "kaufdatum",
    "lieferschein",
    "lieferdatum",
    "leistungsdatum",
    "ausgestellt",
    "ausstellungsdatum",
}
DUE_DATE_LABELS = {
    "fällig",
    "faellig",
    "fällig am",
    "faellig am",
    "zahlbar bis",
    "zahlungsziel",
    "zahlungsfrist",
    "bis zum",
    "due",
    "due date",
    "payable until",
}
PAYMENT_CONTEXT_LABELS = {
    "zahlung erfolgt",
    "bezahlung",
    "kundenbeleg",
    "kartenzahlung",
    "kreditkarte",
    "bar",
    "bar euro",
    "visa",
    "mastercard",
    "maestro",
    "girocard",
    "ec",
    "terminal",
}
TECHNICAL_CONTEXT_LABELS = {
    "tse",
    "start",
    "ende",
    "transaktion",
    "transaktionsnummer",
    "signatur",
    "signaturzähler",
    "signaturzahler",
    "t id",
    "t-id",
    "tid",
    "terminal id",
    "vu nummer",
}
TAX_CONTEXT_LABELS = {
    "mwst",
    "mhst",
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
        candidates = iter_date_candidates(rows)
        scored: list[tuple[float, LayoutDate, str, str]] = []

        for candidate in candidates:
            score, label, explanation = score_date_candidate(candidate, rows, role)
            if score >= 0.58:
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
    result: list[LayoutDate] = []
    for idx, row in enumerate(rows):
        text = _clean_date_text(row.text)
        for match in DATE_PATTERN.finditer(text):
            raw = match.group(1)
            value = _normalize_date_value(raw)
            if value:
                result.append(LayoutDate(value=value, raw=raw, row_index=idx, row=row))
    return result


def score_date_candidate(candidate: LayoutDate, rows: list[LayoutRow], role: str) -> tuple[float, str, str]:
    row_norm = candidate.row.normalized
    idx = candidate.row_index

    context_rows = _row_window(rows, idx, radius=3)
    context_norm = " ".join(row.normalized for row in context_rows)

    row_invoice = _contains_any(row_norm, INVOICE_DATE_LABELS)
    ctx_invoice = _contains_any(context_norm, INVOICE_DATE_LABELS)
    row_due = _contains_any(row_norm, DUE_DATE_LABELS)
    ctx_due = _contains_any(context_norm, DUE_DATE_LABELS)
    row_payment = _contains_any(row_norm, PAYMENT_CONTEXT_LABELS)
    ctx_payment = _contains_any(context_norm, PAYMENT_CONTEXT_LABELS)
    row_tech = _contains_any(row_norm, TECHNICAL_CONTEXT_LABELS)
    ctx_tech = _contains_any(context_norm, TECHNICAL_CONTEXT_LABELS)
    row_tax = _contains_any(row_norm, TAX_CONTEXT_LABELS)

    near_before = rows[max(0, idx - 7) : idx + 1]
    near_after = rows[idx : min(len(rows), idx + 4)]
    near_rows = near_before + near_after

    near_payment = _first_label_in_rows(near_rows, PAYMENT_CONTEXT_LABELS)
    near_invoice = _first_label_in_rows(near_rows, INVOICE_DATE_LABELS)
    near_due = _first_label_in_rows(near_rows, DUE_DATE_LABELS)
    near_money = any(re.search(r"\d{1,6}[,.]\d{2}|\bEUR\b", row.text, re.I) for row in near_rows)

    page_rows = [r for r in rows if r.page == candidate.row.page]
    pos = page_rows.index(candidate.row) / max(1, len(page_rows) - 1) if page_rows else 0.0

    score = 0.10
    reasons: list[str] = []

    if role == "date.due":
        if not (row_due or ctx_due or near_due):
            return 0.0, "", "reject due date without due context"

        if row_due:
            score += 0.88
            reasons.append(f"row_due={row_due}")
        elif ctx_due:
            score += 0.50
            reasons.append(f"context_due={ctx_due}")
        else:
            score += 0.42
            reasons.append(f"near_due={near_due}")

        if row_invoice and not row_due:
            score -= 0.55
            reasons.append(f"row_invoice_penalty={row_invoice}")
        elif ctx_invoice and not row_due:
            score -= 0.14
            reasons.append(f"context_invoice_penalty={ctx_invoice}")

        return max(0.0, score), row_due or ctx_due or near_due, "; ".join(reasons)

    # date.invoice/date.receipt/date.document/date.service
    if row_due and not row_invoice:
        return 0.0, row_due, "reject due row for invoice/document date"

    # Technical timestamps are valid fallback evidence, but lower than business/payment dates.
    if row_tech and not (row_invoice or row_payment):
        if _has_nontechnical_business_or_payment_date(rows, skip_row_index=idx):
            return 0.0, row_tech, "reject technical timestamp because business/payment date exists"
        score += 0.58
        reasons.append(f"technical_timestamp_fallback={row_tech}")
        if pos <= 0.30:
            score += 0.06
            reasons.append("technical_top_section")
        return max(0.0, score), row_tech, "; ".join(reasons)

    if row_invoice:
        score += 0.84
        reasons.append(f"row_invoice={row_invoice}")
    elif ctx_invoice:
        score += 0.44
        reasons.append(f"context_invoice={ctx_invoice}")
    elif near_invoice:
        score += 0.32
        reasons.append(f"near_invoice={near_invoice}")

    # Receipt/payment blocks often contain the only clean business date.
    if row_payment:
        score += 0.42
        reasons.append(f"row_payment={row_payment}")
    elif ctx_payment:
        score += 0.36
        reasons.append(f"context_payment={ctx_payment}")
    elif near_payment:
        score += 0.32
        reasons.append(f"near_payment={near_payment}")

    if near_money and (row_payment or ctx_payment or near_payment):
        score += 0.20
        reasons.append("near_money_in_payment_block")

    if role == "date.service" and "leistungsdatum" in context_norm:
        score += 0.22
        reasons.append("service_label")

    if pos <= 0.20 and (row_invoice or ctx_invoice or near_invoice):
        score += 0.22
        reasons.append("top_section_business_date")
    elif pos >= 0.50 and (row_payment or ctx_payment or near_payment):
        score += 0.24
        reasons.append("lower_payment_section")

    if row_tax:
        score -= 0.20
        reasons.append(f"tax_row_penalty={row_tax}")

    if ctx_tech and not (row_invoice or ctx_invoice or near_invoice or row_payment or ctx_payment or near_payment):
        score -= 0.18
        reasons.append(f"technical_context_penalty={ctx_tech}")

    has_business_context = row_invoice or ctx_invoice or near_invoice or row_payment or ctx_payment or near_payment
    if not has_business_context:
        # Unlabeled top-section date is a weak but useful document-date fallback.
        if pos <= 0.18:
            score += 0.52
            reasons.append("weak_top_section_date_fallback")
            return max(0.0, score), "top_section_date", "; ".join(reasons)
        return 0.0, "", "reject unlabeled/non-payment date"

    label = row_invoice or ctx_invoice or near_invoice or row_payment or ctx_payment or near_payment
    return max(0.0, score), label, "; ".join(reasons)


def _has_nontechnical_business_or_payment_date(rows: list[LayoutRow], *, skip_row_index: int) -> bool:
    for candidate in iter_date_candidates(rows):
        if candidate.row_index == skip_row_index:
            continue

        row_norm = candidate.row.normalized
        context_rows = _row_window(rows, candidate.row_index, radius=3)
        context_norm = " ".join(row.normalized for row in context_rows)

        if _contains_any(row_norm, TECHNICAL_CONTEXT_LABELS):
            continue
        if _contains_any(row_norm, DUE_DATE_LABELS):
            continue

        if _contains_any(row_norm, INVOICE_DATE_LABELS) or _contains_any(context_norm, INVOICE_DATE_LABELS):
            return True

        near_rows = rows[max(0, candidate.row_index - 7) : min(len(rows), candidate.row_index + 4)]
        if _first_label_in_rows(near_rows, PAYMENT_CONTEXT_LABELS):
            return True

    return False


def _row_window(rows: list[LayoutRow], idx: int, radius: int) -> list[LayoutRow]:
    return rows[max(0, idx - radius) : min(len(rows), idx + radius + 1)]


def _first_label_in_rows(rows: list[LayoutRow], labels: set[str]) -> str:
    for row in rows:
        label = _contains_any(row.normalized, labels)
        if label:
            return label
    return ""


def _contains_any(norm: str, labels: set[str]) -> str:
    norm = normalize_label(norm)
    for label in sorted(labels, key=len, reverse=True):
        n_label = normalize_label(label)
        if n_label and n_label in norm:
            return n_label
    return ""


def _clean_date_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("−", "-")
    # OCR often reads O as 0 in date tokens.
    text = re.sub(r"(?i)(?<=\d|[.,;/\-])o(?=\d|[.,;/\-])", "0", text)
    text = re.sub(r"(?i)(?<=\d|[.,;/\-])i(?=\d|[.,;/\-])", "1", text)
    text = re.sub(r"(?i)(?<=\d|[.,;/\-])l(?=\d|[.,;/\-])", "1", text)
    text = re.sub(r"(\d)\s*([.,;/\-])\s*(\d)", r"\1\2\3", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_date_value(raw: str) -> str:
    raw = _clean_date_text(raw)

    # ISO timestamps from TSE/signature/payment blocks must be parsed before
    # fuzzy/dateparser fallback. Otherwise strings like 2026-06-13T... may be
    # misread as 2013-06-26 by locale heuristics.
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?Z?)?", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return ""

    # German/common document dates: 13.06.2026, 13/06/26, 13-06-2026, 13,06,2026.
    m = re.search(r"\b(\d{1,2})[.,;/\-](\d{1,2})[.,;/\-](\d{2,4})\b", raw)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    return ""
