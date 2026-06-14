from paperless_nc_import.extractors.base import ExtractorInput
from paperless_nc_import.extractors.paddleocr_layout_amount import (
    LayoutRecord,
    PaddleOCRLayoutAmountExtractor,
    build_rows,
    iter_money_candidates,
    score_amount_total_candidate,
)


def test_layout_amount_uses_geometry_not_specific_receipt_text():
    records = [
        LayoutRecord("Papier", 0.99, [[22, 271], [333, 271], [333, 321], [22, 321]], 1),
        LayoutRecord("0,85 x 12", 0.90, [[462, 271], [678, 271], [678, 321], [462, 321]], 1),
        LayoutRecord("10,20 A", 0.99, [[714, 271], [872, 271], [872, 321], [714, 321]], 1),
        LayoutRecord("Pfandrückgabe", 0.92, [[22, 765], [333, 765], [333, 812], [22, 812]], 1),
        LayoutRecord("-16,50 B", 0.99, [[685, 761], [854, 761], [854, 815], [685, 815]], 1),
        LayoutRecord("zu zahlen", 0.96, [[22, 909], [216, 909], [216, 960], [22, 960]], 1),
        LayoutRecord(".23,09", 0.91, [[693, 905], [813, 905], [813, 960], [693, 960]], 1),
        LayoutRecord("Kreditkarte", 0.99, [[22, 960], [253, 960], [253, 1010], [22, 1010]], 1),
        LayoutRecord("23.09", 0.94, [[696, 956], [813, 956], [813, 1010], [696, 1010]], 1),
    ]

    rows = build_rows(records)
    cands = iter_money_candidates(rows)
    scored = []
    for cand in cands:
        score, label, explanation = score_amount_total_candidate(cand, cands, rows)
        if score >= 0.65:
            scored.append((score, cand, label, explanation))

    scored.sort(key=lambda x: x[0], reverse=True)
    assert scored
    assert scored[0][1].value == "23,09"
    assert scored[0][2] in {"zu zahlen", "kreditkarte"}


def test_layout_extractor_returns_extractor_result_from_cached_records(monkeypatch, tmp_path):
    from paperless_nc_import.extractors import paddleocr_layout_amount as mod

    records = [
        LayoutRecord("TOTAL", 0.96, [[20, 100], [180, 100], [180, 140], [20, 140]], 1),
        LayoutRecord("68,00", 0.98, [[700, 100], [850, 100], [850, 140], [700, 140]], 1),
        LayoutRecord("BAR EURO", 0.99, [[20, 160], [240, 160], [240, 200], [20, 200]], 1),
        LayoutRecord("68,00", 0.98, [[700, 160], [850, 160], [850, 200], [700, 200]], 1),
    ]

    monkeypatch.setattr(mod, "_load_or_run_paddle_records", lambda path, cfg: records)

    item = ExtractorInput(
        role="amount.total",
        field_type="monetary",
        text="",
        locale="de",
        sources={"path": str(tmp_path / "dummy.pdf"), "paddleocr": {"enabled": True}},
    )
    (tmp_path / "dummy.pdf").write_bytes(b"%PDF")

    result = PaddleOCRLayoutAmountExtractor().extract(item)
    assert result
    assert result[0].value == "68,00"
    assert result[0].backend == "paddleocr_sidecar"
    assert result[0].extractor == "paddleocr_layout_amount_total"
