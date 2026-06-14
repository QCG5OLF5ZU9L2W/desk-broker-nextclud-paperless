from __future__ import annotations

from dataclasses import dataclass
import re

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import (
    compact_iban,
    iban_mod97_valid,
    label_to_regex,
    normalize_date,
    normalize_label,
    normalize_money,
    normalize_ocr_text,
)
from .rulesets import RuleLabel, load_builtin_rulesets

# Requires a decimal separator. This avoids plain quantities and most IDs.
MONEY_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([-+−]?\s*(?:\d(?:[\d\s.]*\d)?\s*[,.]\s*\d\s*\d|\d{1,3}(?:[.\s]\d{3})+(?:[,.]\d{2})|\d+[,.]\d{2}))"
    r"(?![A-Za-z0-9])"
)

DATE_RE = re.compile(
    r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\s*[A-Za-zÄÖÜäöüß]+\s+\d{2,4})\b"
)

IBAN_RE = re.compile(r"\b([A-Z]{2}\s*\d{2}(?:\s*[A-Z0-9]){10,30})\b", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class Line:
    index: int
    text: str
    normalized: str
    start: int


@dataclass(slots=True, frozen=True)
class MoneyHit:
    raw: str
    normalized_value: str
    start: int
    end: int
    line: Line


class GenericTextExtractor(BaseExtractor):
    """Generic local text extractor for invoices, receipts and contracts.

    It is deliberately feature-based, not receipt-specific. Rulesets only provide
    semantic labels. The engine classifies the local line/context and refuses low
    confidence candidates instead of guessing.
    """

    name = "generic_text"
    priority = 50

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        role = (item.role or "").strip().casefold()
        if not role or not item.text:
            return []
        if role.startswith("amount."):
            return self._extract_amount(item)
        if role.startswith("date."):
            return self._extract_date(item)
        if role in {"bank.iban", "iban"}:
            return self._extract_iban(item)
        return []

    def _lines(self, text: str) -> list[Line]:
        body = normalize_ocr_text(text)
        lines: list[Line] = []
        pos = 0
        for idx, raw in enumerate(body.splitlines(True)):
            line_text = raw.rstrip("\r\n")
            lines.append(Line(index=idx, text=line_text, normalized=normalize_label(line_text), start=pos))
            pos += len(raw)
        if not lines and body:
            lines.append(Line(index=0, text=body, normalized=normalize_label(body), start=0))
        return lines

    def _money_hits(self, lines: list[Line]) -> list[MoneyHit]:
        hits: list[MoneyHit] = []
        for line in lines:
            for match in MONEY_RE.finditer(line.text):
                raw = match.group(1)
                normalized = normalize_money(raw)
                if not normalized:
                    continue
                hits.append(
                    MoneyHit(
                        raw=raw,
                        normalized_value=normalized,
                        start=line.start + match.start(1),
                        end=line.start + match.end(1),
                        line=line,
                    )
                )
        return hits

    def _labels_for(self, *, role: str, locale: str) -> list[RuleLabel]:
        labels: list[RuleLabel] = []
        for ruleset in load_builtin_rulesets(locale=locale, role=role):
            labels.extend(ruleset.labels)
        return labels

    def _line_label_matches(self, line_text: str, labels: list[RuleLabel]) -> list[RuleLabel]:
        matches: list[RuleLabel] = []
        for label in labels:
            rx = label_to_regex(label.normalized)
            if re.search(rx, line_text, flags=re.IGNORECASE):
                matches.append(label)
        return matches

    def _nearby_label_matches(
        self, *, lines: list[Line], hit: MoneyHit, labels: list[RuleLabel], radius: int = 1
    ) -> list[RuleLabel]:
        lo = max(0, hit.line.index - radius)
        hi = min(len(lines), hit.line.index + radius + 1)
        text = "\n".join(line.text for line in lines[lo:hi])
        return self._line_label_matches(text, labels)

    def _is_percentage(self, hit: MoneyHit, full_text: str) -> bool:
        before = full_text[max(0, hit.start - 3) : hit.start]
        after = full_text[hit.end : hit.end + 3]
        return "%" in before or "%" in after

    def _is_negative(self, hit: MoneyHit) -> bool:
        return hit.raw.strip().startswith(("-", "−"))

    def _is_unit_price_position(self, hit: MoneyHit) -> bool:
        line = hit.line.text
        rel_start = max(0, hit.start - hit.line.start)
        rel_end = max(rel_start, hit.end - hit.line.start)
        after = line[rel_end : rel_end + 18].casefold()
        before = line[max(0, rel_start - 18) : rel_start].casefold()
        # Generic quantity relation: price directly before/after x quantity.
        return bool(re.search(r"^\s*(?:x|×)\s*[-+]?\d", after)) or bool(
            re.search(r"[-+]?\d\s*(?:x|×)\s*$", before)
        )

    def _is_tax_context(self, hit: MoneyHit) -> bool:
        norm = hit.line.normalized
        return any(token in norm for token in {"mwst", "mwsteuer", "ust", "umsatzsteuer", "netto", "brutto", "steuer"})

    def _is_refund_or_discount_context(self, hit: MoneyHit) -> bool:
        norm = hit.line.normalized
        return any(token in norm for token in {"rabatt", "retoure", "rueckgabe", "rückgabe", "storno", "gutschrift", "pfandrueckgabe", "pfandrückgabe"})

    def _amount_total_score(
        self,
        *,
        item: ExtractorInput,
        lines: list[Line],
        hit: MoneyHit,
        labels: list[RuleLabel],
        all_hits: list[MoneyHit],
        full_text: str,
    ) -> tuple[float, str, str, str]:
        if self._is_percentage(hit, full_text):
            return 0.0, "", "", "reject_percentage"
        if self._is_negative(hit):
            return 0.0, "", "", "reject_negative"
        if self._is_unit_price_position(hit):
            return 0.0, "", "", "reject_unit_price"

        line_matches = self._line_label_matches(hit.line.text, labels)
        nearby_matches = self._nearby_label_matches(lines=lines, hit=hit, labels=labels, radius=1)
        matches = line_matches or nearby_matches
        if not matches:
            return 0.0, "", "", "reject_unlabeled"

        best = max(matches, key=lambda lab: lab.weight)
        kind = (best.kind or "label").casefold()
        line_has_strong = any((lab.kind or "").casefold() in {"strong_total", "payment_confirmation"} for lab in line_matches)

        if self._is_tax_context(hit) and kind not in {"strong_total", "payment_confirmation"}:
            return 0.0, "", "", "reject_tax_context"
        if self._is_refund_or_discount_context(hit) and kind != "strong_total":
            return 0.0, "", "", "reject_refund_discount_context"

        score = best.weight
        extractor = "generic_amount_label"
        if kind == "strong_total":
            score += 0.12
            extractor = "generic_amount_total_label"
        elif kind == "payment_confirmation":
            score += 0.03
            extractor = "generic_amount_payment_confirmation"
        elif kind in {"weak_total", "label"}:
            score -= 0.18

        if line_matches:
            score += 0.06
        else:
            score -= 0.10

        # Position is weak evidence only. It helps receipts but never replaces labels.
        if lines:
            score += min(0.06, hit.line.index / max(1, len(lines) - 1) * 0.06)

        # A matching payment line elsewhere confirms the candidate.
        same_value_hits = [other for other in all_hits if other.normalized_value == hit.normalized_value]
        if len(same_value_hits) >= 2:
            payment_labels = [lab for lab in labels if (lab.kind or "").casefold() == "payment_confirmation"]
            if any(self._line_label_matches(other.line.text, payment_labels) for other in same_value_hits):
                score += 0.10

        # If the line has only weak label and looks like a normal item row, do not prefill.
        if not line_has_strong and re.search(r"\b(?:x|×)\s*\d+\b|\b\d+\s*(?:x|×)\b", hit.line.text.casefold()):
            score -= 0.25

        return max(0.0, min(1.0, score)), best.normalized, extractor, f"label={best.normalized};kind={kind}"

    def _extract_amount(self, item: ExtractorInput) -> list[ExtractorResult]:
        lines = self._lines(item.text)
        labels = self._labels_for(role=item.role, locale=item.locale)
        hits = self._money_hits(lines)
        full_text = normalize_ocr_text(item.text)
        results: list[ExtractorResult] = []
        for hit in hits:
            if item.role == "amount.total":
                score, label, extractor, explanation = self._amount_total_score(
                    item=item,
                    lines=lines,
                    hit=hit,
                    labels=labels,
                    all_hits=hits,
                    full_text=full_text,
                )
                min_conf = 0.62
            else:
                matched = self._line_label_matches(hit.line.text, labels)
                if not matched or self._is_percentage(hit, full_text):
                    continue
                best = max(matched, key=lambda lab: lab.weight)
                score = best.weight + 0.05
                label = best.normalized
                extractor = f"generic_{item.role.replace('.', '_')}_label"
                explanation = f"label={label};kind={best.kind}"
                min_conf = 0.55
            if score < min_conf:
                continue
            results.append(
                ExtractorResult(
                    role=item.role,
                    field_type=item.field_type,
                    value=hit.normalized_value,
                    raw_value=hit.raw,
                    label_normalized=label,
                    extractor=extractor,
                    backend=self.name,
                    confidence=score,
                    explanation=explanation,
                )
            )
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def _extract_date(self, item: ExtractorInput) -> list[ExtractorResult]:
        lines = self._lines(item.text)
        labels = self._labels_for(role=item.role, locale=item.locale)
        results: list[ExtractorResult] = []
        for line in lines:
            matched = self._line_label_matches(line.text, labels)
            if not matched:
                continue
            best = max(matched, key=lambda lab: lab.weight)
            for match in DATE_RE.finditer(line.text):
                raw = match.group(1)
                normalized = normalize_date(raw)
                if not normalized:
                    continue
                score = min(1.0, best.weight + 0.10)
                results.append(
                    ExtractorResult(
                        role=item.role,
                        field_type=item.field_type,
                        value=normalized,
                        raw_value=raw,
                        label_normalized=best.normalized,
                        extractor="generic_date_label",
                        backend=self.name,
                        confidence=score,
                        explanation=f"label={best.normalized};kind={best.kind}",
                    )
                )
                break
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def _extract_iban(self, item: ExtractorInput) -> list[ExtractorResult]:
        labels = self._labels_for(role="bank.iban", locale=item.locale)
        lines = self._lines(item.text)
        results: list[ExtractorResult] = []
        for line in lines:
            matched = self._line_label_matches(line.text, labels)
            for match in IBAN_RE.finditer(line.text):
                raw = match.group(1)
                value = compact_iban(raw)
                valid = iban_mod97_valid(value)
                if not valid:
                    try:  # pragma: no cover - optional dependency branch
                        from stdnum import iban as stdnum_iban  # type: ignore

                        valid = bool(stdnum_iban.is_valid(value))
                    except Exception:
                        valid = False
                if not valid:
                    continue
                label = max(matched, key=lambda lab: lab.weight).normalized if matched else "iban"
                score = 0.95 if matched else 0.82
                results.append(
                    ExtractorResult(
                        role="bank.iban",
                        field_type=item.field_type,
                        value=value,
                        raw_value=raw,
                        label_normalized=label,
                        extractor="generic_iban_checksum",
                        backend=self.name,
                        confidence=score,
                        explanation="iban_checksum_valid",
                    )
                )
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results
