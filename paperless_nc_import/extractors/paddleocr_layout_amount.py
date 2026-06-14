from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import normalize_label, normalize_money


MONEY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([-+−]?\s*[.,]?\s*\d{1,6}(?:[.,]\s*\d{2})|[-+−]?\s*\d{1,3}(?:[.\s]\d{3})+[,.]\s*\d{2})"
    r"(?![A-Za-z0-9])"
)

TOTAL_LABELS = {
    "total",
    "summe",
    "sumne",
    "endsumme",
    "end summe",
    "gesamt",
    "gesamtbetrag",
    "rechnungsbetrag",
    "betrag",
    "zu zahlen",
    "zahlbetrag",
    "saldo",
    "faktura",
    "rechnung",
    "bar euro",
}
PAYMENT_LABELS = {
    "bar",
    "kreditkarte",
    "kartenzahlung",
    "karte",
    "visa",
    "mastercard",
    "maestro",
    "ec",
    "ec cash",
    "girocard",
    "bezahlung",
}
TAX_LABELS = {"mwst", "mhst", "ust", "umsatzsteuer", "netto", "brutto", "steuer", "tax", "vat"}
NEGATIVE_CONTEXT = {"rabatt", "retoure", "rueckgabe", "rückgabe", "storno", "gutschrift", "pfandrueckgabe", "pfandrückgabe"}
ITEM_HINTS = {"menge", "art", "artikel", "bezeichnung", "qty", "anzahl"}


@dataclass(slots=True, frozen=True)
class LayoutRecord:
    text: str
    score: float | None
    box: Any
    page: int = 1

    @property
    def x(self) -> float:
        return _xywh(self.box)[0]

    @property
    def y(self) -> float:
        return _xywh(self.box)[1]

    @property
    def w(self) -> float:
        return _xywh(self.box)[2]

    @property
    def h(self) -> float:
        return _xywh(self.box)[3]

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0


@dataclass(slots=True, frozen=True)
class LayoutRow:
    page: int
    records: tuple[LayoutRecord, ...]

    @property
    def y(self) -> float:
        return median([r.cy for r in self.records]) if self.records else 0.0

    @property
    def text(self) -> str:
        return " ".join(r.text for r in sorted(self.records, key=lambda r: r.x) if r.text).strip()

    @property
    def normalized(self) -> str:
        return normalize_label(self.text)


@dataclass(slots=True, frozen=True)
class LayoutMoney:
    value: str
    raw: str
    record: LayoutRecord
    row_index: int
    row: LayoutRow


class PaddleOCRLayoutAmountExtractor(BaseExtractor):
    name = "paddleocr_layout"
    priority = 42

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        role = (item.role or "").casefold()
        if role != "amount.total":
            return []
        path = _source_path(item.sources or {})
        if not path:
            return []
        pdf = Path(path).expanduser()
        if not pdf.exists():
            return []

        cfg = _load_paddle_config(item.sources or {})
        if not cfg.get("enabled"):
            return []

        records = _load_or_run_paddle_records(pdf, cfg)
        if not records:
            return []

        rows = build_rows(records)
        candidates = list(iter_money_candidates(rows))
        if not candidates:
            return []

        scored: list[tuple[float, LayoutMoney, str, str]] = []
        for cand in candidates:
            score, label, explanation = score_amount_total_candidate(cand, candidates, rows)
            if score >= 0.65:
                scored.append((score, cand, label, explanation))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[ExtractorResult] = []
        for score, cand, label, explanation in scored[:5]:
            results.append(
                ExtractorResult(
                    role="amount.total",
                    field_type=item.field_type,
                    value=cand.value,
                    raw_value=cand.raw,
                    label_normalized=label,
                    extractor="paddleocr_layout_amount_total",
                    backend="paddleocr_sidecar",
                    confidence=min(0.99, round(score, 3)),
                    explanation=explanation,
                )
            )
        return results


def _source_path(sources: dict[str, Any]) -> str | None:
    for key in ("path", "file_path", "pdf_path", "source_path", "local_path", "filename"):
        value = sources.get(key)
        if value:
            return str(value)
    return None


def _xywh(box: Any) -> tuple[float, float, float, float]:
    if not box:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(x, (int, float)) for x in box):
        x1, y1, x2, y2 = [float(x) for x in box]
        return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)
    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _fix_ocr_money_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("€", " EUR ")
    text = text.replace("−", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<!\d)[\.,]\s*(\d{1,6})[,.]\s*(\d{2})(?!\d)", r"\1,\2", text)
    text = re.sub(r"(?<!\d)(\d{1,6})\.(\d{2})(?!\d)", r"\1,\2", text)
    text = re.sub(r"(\d+)\.,(\d{2})", r"\1,\2", text)
    text = re.sub(r"(?i)\b[a-z]{1,6}(\d{1,6},\d{2}\s*EUR\b)", r"\1", text)
    return text.strip()


def _record_from_dict(raw: dict[str, Any]) -> LayoutRecord | None:
    text = _fix_ocr_money_text(str(raw.get("text") or ""))
    if not text:
        return None
    score = raw.get("score")
    try:
        score = float(score) if score is not None else None
    except Exception:
        score = None
    page = raw.get("page", 1)
    try:
        page = int(page)
    except Exception:
        page = 1
    return LayoutRecord(text=text, score=score, box=raw.get("box"), page=page)


def build_rows(records: list[LayoutRecord], *, min_score: float = 0.50) -> list[LayoutRow]:
    usable = [r for r in records if r.text and (r.score is None or r.score >= min_score)]
    rows: list[LayoutRow] = []

    for page in sorted({r.page for r in usable}):
        page_records = sorted([r for r in usable if r.page == page], key=lambda r: (r.cy, r.x))
        heights = [max(8.0, r.h) for r in page_records if r.h > 0]
        row_threshold = max(18.0, median(heights) * 0.70) if heights else 24.0

        grouped: list[list[LayoutRecord]] = []
        for rec in page_records:
            placed = False
            for row in grouped:
                row_cy = median([x.cy for x in row])
                if abs(rec.cy - row_cy) <= row_threshold:
                    row.append(rec)
                    placed = True
                    break
            if not placed:
                grouped.append([rec])

        for row in grouped:
            row.sort(key=lambda r: r.x)
            rows.append(LayoutRow(page=page, records=tuple(row)))

    rows.sort(key=lambda r: (r.page, r.y))
    return rows


def iter_money_candidates(rows: list[LayoutRow]) -> list[LayoutMoney]:
    hits: list[LayoutMoney] = []
    for row_idx, row in enumerate(rows):
        for rec in row.records:
            text = _fix_ocr_money_text(rec.text)
            for match in MONEY_TOKEN_RE.finditer(text):
                raw = match.group(1)
                value = normalize_money(raw)
                if not value:
                    continue
                hits.append(LayoutMoney(value=value, raw=raw, record=rec, row_index=row_idx, row=row))
    return hits


def _contains_any(norm: str, words: set[str]) -> str:
    for word in sorted(words, key=len, reverse=True):
        if word in norm:
            return word
    return ""


def _row_window(rows: list[LayoutRow], idx: int, radius: int = 2) -> list[LayoutRow]:
    return rows[max(0, idx - radius) : min(len(rows), idx + radius + 1)]


def _is_negative(cand: LayoutMoney) -> bool:
    return cand.raw.strip().startswith(("-", "−")) or cand.value.strip().startswith("-")


def _is_quantity_or_unit_row(cand: LayoutMoney) -> bool:
    text = cand.row.text.casefold()
    raw = re.escape(cand.raw.strip())
    if re.search(r"\d+[,.]\d{2}\s*(x|×)\s*-?\d+", text):
        money_records = [h for h in iter_money_candidates([cand.row]) if h.value]
        if money_records and cand.record.x >= max(h.record.x for h in money_records):
            return False
        return True
    if re.search(r"(x|×)\s*-?\d+", text) and re.search(raw, text):
        if cand.record.x < 0.65 * max([r.x + r.w for r in cand.row.records] or [cand.record.x + cand.record.w]):
            return True
    return False


def _is_tax_row_without_total_context(cand: LayoutMoney, context_norm: str) -> bool:
    row_norm = cand.row.normalized
    if _contains_any(row_norm, TAX_LABELS):
        if not _contains_any(context_norm, TOTAL_LABELS | PAYMENT_LABELS):
            return True
        if "%" in cand.row.text or re.search(r"\b(7|19)\s*%", cand.row.text):
            return True
    return False


def _same_value_repeated_near_payment(cand: LayoutMoney, all_cands: list[LayoutMoney], rows: list[LayoutRow]) -> bool:
    for other in all_cands:
        if other is cand:
            continue
        if other.value != cand.value:
            continue
        if abs(other.row_index - cand.row_index) > 5:
            continue
        context = " ".join(r.normalized for r in _row_window(rows, other.row_index, radius=1))
        if _contains_any(context, PAYMENT_LABELS | TOTAL_LABELS):
            return True
    return False


def score_amount_total_candidate(
    cand: LayoutMoney,
    all_cands: list[LayoutMoney],
    rows: list[LayoutRow],
) -> tuple[float, str, str]:
    if _is_negative(cand):
        return 0.0, "", "reject negative amount"
    if _is_quantity_or_unit_row(cand):
        return 0.0, "", "reject quantity/unit row"

    context_rows = _row_window(rows, cand.row_index, radius=2)
    context_norm = " ".join(row.normalized for row in context_rows)
    row_norm = cand.row.normalized

    total_label = _contains_any(row_norm, TOTAL_LABELS) or _contains_any(context_norm, TOTAL_LABELS)
    payment_label = _contains_any(row_norm, PAYMENT_LABELS) or _contains_any(context_norm, PAYMENT_LABELS)
    negative_label = _contains_any(context_norm, NEGATIVE_CONTEXT)

    if negative_label and not total_label:
        return 0.0, negative_label, "reject refund/discount context"
    if _is_tax_row_without_total_context(cand, context_norm):
        return 0.0, "", "reject tax row"

    score = 0.10
    reason: list[str] = []

    if total_label:
        score += 0.62
        reason.append(f"total_label={total_label}")
    if payment_label:
        score += 0.36
        reason.append(f"payment_label={payment_label}")

    row_width = max([r.x + r.w for r in cand.row.records] or [cand.record.x + cand.record.w])
    if row_width > 0 and cand.record.x >= row_width * 0.55:
        score += 0.12
        reason.append("right_column")

    page_rows = [r for r in rows if r.page == cand.row.page]
    if page_rows:
        position = page_rows.index(cand.row) / max(1, len(page_rows) - 1)
        if position >= 0.45:
            score += 0.10
            reason.append("lower_half")
        if position >= 0.65:
            score += 0.08
            reason.append("bottom_section")

    if _same_value_repeated_near_payment(cand, all_cands, rows):
        score += 0.18
        reason.append("same_value_repeated_near_payment")

    if _contains_any(row_norm, ITEM_HINTS) and not (total_label or payment_label):
        score -= 0.25
        reason.append("item_header_penalty")

    if _contains_any(row_norm, TAX_LABELS):
        score -= 0.20
        reason.append("tax_row_penalty")

    if not (total_label or payment_label):
        return 0.0, "", "reject unlabeled layout amount"

    label = total_label or payment_label
    return max(0.0, score), label, "; ".join(reason)


def _config_path() -> Path:
    return Path(os.environ.get("PAPERLESS_NC_IMPORT_CONFIG", "~/.config/paperless-nc-import/config.yaml")).expanduser()


def _load_paddle_config(sources: dict[str, Any]) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    path = _config_path()
    if yaml is not None and path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                backends = data.get("ocr_backends") or {}
                if isinstance(backends, dict) and isinstance(backends.get("paddleocr"), dict):
                    cfg.update(backends["paddleocr"])
        except Exception:
            pass

    source_cfg = sources.get("paddleocr") if isinstance(sources.get("paddleocr"), dict) else {}
    cfg.update(source_cfg)

    if os.environ.get("PAPERLESS_NC_IMPORT_PADDLEOCR_ENABLED") is not None:
        cfg["enabled"] = os.environ["PAPERLESS_NC_IMPORT_PADDLEOCR_ENABLED"].lower() in {"1", "true", "yes", "on"}
    if os.environ.get("PAPERLESS_NC_IMPORT_PADDLEOCR_PYTHON"):
        cfg["python"] = os.environ["PAPERLESS_NC_IMPORT_PADDLEOCR_PYTHON"]
    if os.environ.get("PAPERLESS_NC_IMPORT_PADDLEOCR_CACHE_DIR"):
        cfg["cache_dir"] = os.environ["PAPERLESS_NC_IMPORT_PADDLEOCR_CACHE_DIR"]

    cfg.setdefault("enabled", False)
    cfg.setdefault("python", "~/.local/share/paperless-nc-import/paddleocr-sidecar/.venv/bin/python")
    cfg.setdefault("cache_dir", "~/.local/share/paperless-nc-import/paddleocr-sidecar")
    cfg.setdefault("dpi", 300)
    cfg.setdefault("max_pages", 3)
    cfg.setdefault("min_score", 0.50)
    cfg.setdefault("timeout", 180)
    cfg.setdefault("run_policy", "on_demand")

    return cfg


def _run_worker(path: Path, cfg: dict[str, Any]) -> Path | None:
    py = Path(str(cfg.get("python") or "")).expanduser()
    if not py.exists():
        return None

    cache_dir = Path(str(cfg.get("cache_dir") or "~/.cache/paperless-nc-import/paddleocr")).expanduser()
    out = cache_dir / "out"
    out.mkdir(parents=True, exist_ok=True)

    worker = Path(__file__).with_name("paddleocr_worker.py")
    if not worker.exists():
        return None

    cmd = [
        str(py),
        str(worker),
        "--input",
        str(path),
        "--output",
        str(out),
        "--dpi",
        str(int(cfg.get("dpi", 300))),
        "--max-pages",
        str(int(cfg.get("max_pages", 3))),
        "--min-score",
        str(float(cfg.get("min_score", 0.50))),
    ]

    timeout = int(cfg.get("timeout", 180))
    if str(cfg.get("run_policy", "on_demand")).lower() == "cache_only":
        timeout = min(3, timeout)

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env={**os.environ, "FLAGS_use_mkldnn": "0", "FLAGS_enable_pir_api": "0"},
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    try:
        info = json.loads(proc.stdout.strip().splitlines()[-1])
        json_path = Path(info["json"])
        if json_path.exists():
            return json_path
    except Exception:
        return None
    return None


def _load_or_run_paddle_records(path: Path, cfg: dict[str, Any]) -> list[LayoutRecord]:
    json_path = _run_worker(path, cfg)
    if not json_path:
        return []

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    raw_records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(raw_records, list):
        return []

    records: list[LayoutRecord] = []
    for raw in raw_records:
        if isinstance(raw, dict):
            rec = _record_from_dict(raw)
            if rec:
                records.append(rec)
    return records
