from paperless_nc_import.extractors.paddleocr_worker import OCRRecord, records_to_layout_text


def test_records_to_layout_text_preserves_label_amount_geometry():
    records = [
        OCRRecord("zu zahlen", 0.96, [[22, 909], [216, 909], [216, 960], [22, 960]], 1),
        OCRRecord(".23,09", 0.91, [[693, 905], [813, 905], [813, 960], [693, 960]], 1),
        OCRRecord("Kreditkarte", 0.99, [[22, 960], [253, 960], [253, 1010], [22, 1010]], 1),
        OCRRecord("23.09", 0.94, [[696, 956], [813, 956], [813, 1010], [696, 1010]], 1),
    ]
    text = records_to_layout_text(records)
    assert "zu zahlen 23,09" in text
    assert "Kreditkarte 23,09" in text


def test_records_to_layout_text_filters_low_confidence_noise():
    records = [
        OCRRecord("zu zahlen", 0.96, [[22, 909], [216, 909], [216, 960], [22, 960]], 1),
        OCRRecord("23,09", 0.94, [[693, 905], [813, 905], [813, 960], [693, 960]], 1),
        OCRRecord("kaputt", 0.10, [[10, 1000], [100, 1000], [100, 1050], [10, 1050]], 1),
    ]
    text = records_to_layout_text(records, min_score=0.50)
    assert "zu zahlen 23,09" in text
    assert "kaputt" not in text
