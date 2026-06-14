from __future__ import annotations

from .base import ExtractorInput, ExtractorResult
from .generic_text import GenericTextExtractor
from .invoice2data_adapter import Invoice2DataExtractor
from .structured_invoice import StructuredInvoiceExtractor


def extractor_chain() -> list:
    chain = [
        StructuredInvoiceExtractor(),
        Invoice2DataExtractor(),
        GenericTextExtractor(),
    ]
    return sorted(chain, key=lambda ex: int(getattr(ex, "priority", 100)))


def extract_role_values(
    *,
    role: str,
    field_type: str,
    text: str,
    locale: str = "de",
    sources: dict[str, str] | None = None,
) -> list[ExtractorResult]:
    item = ExtractorInput(
        role=role,
        field_type=field_type,
        text=text,
        locale=locale,
        sources=sources or {},
    )
    results: list[ExtractorResult] = []
    for extractor in extractor_chain():
        try:
            found = extractor.extract(item)
        except Exception:
            found = []
        if found:
            results.extend(found)
            # Higher-priority structured/template extractors are authoritative.
            if getattr(extractor, "name", "") in {"structured_invoice", "invoice2data"}:
                break
    results.sort(key=lambda result: result.confidence, reverse=True)
    return results


def extract_role_value(
    *,
    role: str,
    field_type: str,
    text: str,
    locale: str = "de",
    sources: dict[str, str] | None = None,
) -> ExtractorResult | None:
    results = extract_role_values(
        role=role,
        field_type=field_type,
        text=text,
        locale=locale,
        sources=sources,
    )
    return results[0] if results else None
