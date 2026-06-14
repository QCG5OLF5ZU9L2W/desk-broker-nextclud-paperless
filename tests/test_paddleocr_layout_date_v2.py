from paperless_nc_import.extractors.base import ExtractorInput
from paperless_nc_import.extractors.paddleocr_layout_amount import LayoutRecord
from paperless_nc_import.extractors.paddleocr_layout_date import (
    PaddleOCRLayoutDateExtractor,
    _normalize_date_value,
    build_rows,
    iter_date_candidates,
    score_date_candidate,
)


def best(records, role):
    rows = build_rows(records)
    scored = []
    for c in iter_date_candidates(rows):
        score, label, why = score_date_candidate(c, rows, role)
        if score >= 0.58:
            scored.append((score, c.value, label, why, c.raw))
    scored.sort(reverse=True)
    return scored[0] if scored else None


def test_deterministic_date_normalizer_iso_and_de():
    assert _normalize_date_value("2026-06-13T15:52:20.000Z") == "2026-06-13"
    assert _normalize_date_value("13.06.2026") == "2026-06-13"
    assert _normalize_date_value("13,06,2026") == "2026-06-13"
    assert _normalize_date_value("04.05.26") == "2026-05-04"


def test_explicit_document_date_label():
    records = [
        LayoutRecord("Datum:", 0.99, [[20, 100], [160, 100], [160, 140], [20, 140]], 1),
        LayoutRecord("04.05.2026 14:26", 0.99, [[260, 100], [600, 100], [600, 140], [260, 140]], 1),
    ]
    assert best(records, "date.invoice")[1] == "2026-05-04"


def test_rechnung_vom_document_date():
    records = [
        LayoutRecord("RECHNUNG NR. 51624 vom 28.05.2026", 0.95, [[20, 100], [850, 100], [850, 150], [20, 150]], 1),
    ]
    assert best(records, "date.invoice")[1] == "2026-05-28"


def test_due_date_prefers_due_row():
    records = [
        LayoutRecord("Rechnungsdatum: 14.06.2026", 0.99, [[20, 100], [500, 100], [500, 140], [20, 140]], 1),
        LayoutRecord("Fällig am: 30.06.2026", 0.99, [[20, 160], [500, 160], [500, 200], [20, 200]], 1),
    ]
    assert best(records, "date.due")[1] == "2026-06-30"


def test_payment_block_date_beats_technical_timestamp():
    records = [
        LayoutRecord("Start 2026-06-13T15:52:20.000Z", 0.90, [[20, 100], [850, 100], [850, 150], [20, 150]], 1),
        LayoutRecord("Ende 2026-06-13T15:53:09.000Z", 0.94, [[20, 160], [850, 160], [850, 210], [20, 210]], 1),
        LayoutRecord("KUNDENBELEG", 0.95, [[190, 400], [630, 400], [630, 450], [190, 450]], 1),
        LayoutRecord("Bezahlung VISA", 0.78, [[230, 455], [870, 455], [870, 510], [230, 510]], 1),
        LayoutRecord("23,09 EUR", 0.85, [[460, 520], [850, 520], [850, 570], [460, 570]], 1),
        LayoutRecord("13.06.2026", 0.99, [[26, 600], [234, 600], [234, 650], [26, 650]], 1),
        LayoutRecord("T-ID 60157490", 0.95, [[530, 600], [835, 600], [835, 650], [530, 650]], 1),
    ]
    assert best(records, "date.invoice")[1] == "2026-06-13"


def test_technical_timestamp_is_valid_fallback():
    records = [
        LayoutRecord("Start 2026-06-13T15:52:20.000Z", 0.90, [[20, 100], [850, 100], [850, 150], [20, 150]], 1),
        LayoutRecord("Ende 2026-06-13T15:53:09.000Z", 0.94, [[20, 160], [850, 160], [850, 210], [20, 210]], 1),
        LayoutRecord("TSE Transaktionsnummer: 247696", 0.94, [[20, 220], [850, 220], [850, 260], [20, 260]], 1),
    ]
    assert best(records, "date.invoice")[1] == "2026-06-13"


def test_layout_date_extractor_cached_records(monkeypatch, tmp_path):
    from paperless_nc_import.extractors import paddleocr_layout_date as mod

    records = [
        LayoutRecord("Datum:", 0.99, [[20, 100], [160, 100], [160, 140], [20, 140]], 1),
        LayoutRecord("13.06.2026", 0.99, [[260, 100], [500, 100], [500, 140], [260, 140]], 1),
    ]
    monkeypatch.setattr(mod, "_load_or_run_paddle_records", lambda path, cfg: records)

    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"%PDF")

    item = ExtractorInput(
        role="date.invoice",
        field_type="date",
        text="",
        locale="de",
        sources={"path": str(pdf), "paddleocr": {"enabled": True}},
    )

    result = PaddleOCRLayoutDateExtractor().extract(item)
    assert result
    assert result[0].value == "2026-06-13"
    assert result[0].backend == "paddleocr_sidecar"
