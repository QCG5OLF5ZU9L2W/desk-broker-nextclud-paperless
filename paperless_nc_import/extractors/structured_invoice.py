from __future__ import annotations

from .base import BaseExtractor, ExtractorInput, ExtractorResult
from .normalizers import normalize_date, normalize_money


class StructuredInvoiceExtractor(BaseExtractor):
    """Optional adapter for Factur-X/ZUGFeRD/XRechnung sources.

    This adapter is intentionally defensive: if optional dependencies or a
    structured invoice payload are missing, it returns no result. The generic
    text extractor remains the fallback. Future versions can map XML elements
    more completely without changing the GUI contract.
    """

    name = "structured_invoice"
    priority = 10

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        path = item.path
        if not path or path.suffix.casefold() != ".pdf" or not path.exists():
            return []
        try:  # pragma: no cover - optional dependency branch
            from facturx import get_facturx_xml_from_pdf  # type: ignore
        except Exception:
            return []

        try:  # pragma: no cover - optional dependency branch
            xml_bytes = get_facturx_xml_from_pdf(str(path))
        except Exception:
            return []
        if not xml_bytes:
            return []

        # Minimal namespace-free extraction. This deliberately avoids keeping or
        # exporting XML content. It only maps local values to the requested role.
        try:  # pragma: no cover - optional dependency branch
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_bytes)
        except Exception:
            return []

        role = (item.role or "").casefold()
        candidates: list[ExtractorResult] = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1].casefold()
            text = (elem.text or "").strip()
            if not text:
                continue
            if role == "date.invoice" and tag in {"issuedatetime", "date"}:
                value = normalize_date(text)
                if value:
                    candidates.append(
                        ExtractorResult(
                            role=role,
                            field_type=item.field_type,
                            value=value,
                            raw_value=text,
                            label_normalized="structured invoice date",
                            extractor="facturx_xml",
                            backend=self.name,
                            confidence=0.99,
                        )
                    )
            if role == "amount.total" and tag in {"grandtotalamount", "dupayableamount"}:
                value = normalize_money(text)
                if value:
                    candidates.append(
                        ExtractorResult(
                            role=role,
                            field_type=item.field_type,
                            value=value,
                            raw_value=text,
                            label_normalized="structured invoice total",
                            extractor="facturx_xml",
                            backend=self.name,
                            confidence=0.99,
                        )
                    )
        candidates.sort(key=lambda r: r.confidence, reverse=True)
        return candidates
