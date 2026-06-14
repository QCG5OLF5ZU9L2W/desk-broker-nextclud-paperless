from paperless_nc_import.extractors.base import ExtractorInput
from paperless_nc_import.extractors.paddleocr_layout_amount import LayoutRecord
from paperless_nc_import.extractors.paddleocr_layout_date import (
    PaddleOCRLayoutDateExtractor,
    build_rows,
    iter_date_candidates,
    score_date_candidate,
)


def test_layout_date_invoice_explicit_datum():
    records = [
        LayoutRecord("Verkauf", 0.95, [[20, 100], [200, 100], [200, 140], [20, 140]], 1),
        LayoutRecord("Datum:", 0.98, [[20, 180], [180, 180], [180, 220], [20, 220]], 1),
        LayoutRecord("04.05.2026 14:26", 0.99, [[260, 180], [620, 180], [620, 220], [260, 220]], 1),
        LayoutRecord("Start 2026-05-04T13:26:00Z", 0.99, [[20, 900], [700, 900], [700, 940], [20, 940]], 1),
    ]

    rows = build_rows(records)
    cands = iter_date_candidates(rows)
    scored = [(*score_date_candidate(c, rows, "date.invoice"), c) for c in cands]
    scored = [(score, label, why, cand) for score, label, why, cand in scored if score >= 0.62]
    scored.sort(key=lambda x: x[0], reverse=True)

    assert scored
    assert scored[0][3].value == "2026-05-04"
    assert "datum" in scored[0][1]


def test_layout_date_invoice_rechnung_vom():
    records = [
        LayoutRecord("RECHNUNG NR. 51624 vom 28.05.2026", 0.95, [[20, 100], [850, 100], [850, 150], [20, 150]], 1),
        LayoutRecord("Start 2026-05-28T13:58:55.000Z", 0.99, [[20, 900], [850, 900], [850, 950], [20, 950]], 1),
    ]

    rows = build_rows(records)
    cands = iter_date_candidates(rows)
    scored = [(*score_date_candidate(c, rows, "date.invoice"), c) for c in cands]
    scored = [(score, label, why, cand) for score, label, why, cand in scored if score >= 0.62]
    scored.sort(key=lambda x: x[0], reverse=True)

    assert scored
    assert scored[0][3].value == "2026-05-28"
    assert "rechnung" in scored[0][1] or "vom" in scored[0][1]


def test_layout_date_due_requires_due_label():
    records = [
        LayoutRecord("Rechnungsdatum: 14.06.2026", 0.99, [[20, 100], [500, 100], [500, 140], [20, 140]], 1),
        LayoutRecord("Fällig am: 30.06.2026", 0.99, [[20, 160], [500, 160], [500, 200], [20, 200]], 1),
    ]

    rows = build_rows(records)
    cands = iter_date_candidates(rows)
    scored = [(*score_date_candidate(c, rows, "date.due"), c) for c in cands]
    scored = [(score, label, why, cand) for score, label, why, cand in scored if score >= 0.62]
    scored.sort(key=lambda x: x[0], reverse=True)

    assert scored
    assert scored[0][3].value == "2026-06-30"
    assert "fällig" in scored[0][1] or "faellig" in scored[0][1]


def test_layout_date_extractor_uses_cached_records(monkeypatch, tmp_path):
    from paperless_nc_import.extractors import paddleocr_layout_date as mod

    records = [
        LayoutRecord("Datum:", 0.99, [[20, 100], [160, 100], [160, 140], [20, 140]], 1),
        LayoutRecord("13.06.2026", 0.99, [[260, 100], [500, 100], [500, 140], [260, 140]], 1),
        LayoutRecord("Ende 2026-06-13T15:53:09.000Z", 0.99, [[20, 900], [800, 900], [800, 940], [20, 940]], 1),
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
    assert result[0].extractor == "paddleocr_layout_date"
