from paperless_nc_import.extraction import (
    CustomFieldExtractionRule,
    extract_custom_field_value,
    normalize_monetary,
)


def test_normalize_monetary_from_dot_decimal_for_gui():
    assert normalize_monetary("14.64") == "14,64"


def test_normalize_monetary_from_comma_decimal_for_gui():
    assert normalize_monetary("1.234,56 €") == "1234,56"


def test_extract_custom_field_value_by_id():
    rule = CustomFieldExtractionRule(
        field_id=3,
        patterns=[r"Endsumme\s*€?\s*([0-9]+[,.][0-9]{2})"],
        normalize="monetary",
    )
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="Endsumme € 14.64",
        rules=[rule],
    )
    assert result is not None
    assert result.value == "14,64"


def test_extract_custom_field_value_ignores_name_when_id_is_set():
    rule = CustomFieldExtractionRule(
        field_id=3,
        field_name="Rechnungsbetrag",
        patterns=[r"Endsumme\s*€?\s*([0-9]+[,.][0-9]{2})"],
        normalize="monetary",
    )
    assert (
        extract_custom_field_value(
            field_id=4,
            field_name="Rechnungsbetrag",
            field_type="monetary",
            text="Endsumme € 14.64",
            rules=[rule],
        )
        is None
    )


def test_extract_custom_field_value_by_name_fallback():
    rule = CustomFieldExtractionRule(
        field_name="Rechnungsbetrag",
        patterns=[r"Endsumme\s*€?\s*([0-9]+[,.][0-9]{2})"],
        normalize="monetary",
    )
    result = extract_custom_field_value(
        field_id=99,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="Endsumme € 14.64",
        rules=[rule],
    )
    assert result is not None
    assert result.value == "14,64"


def test_builtin_receipt_total_extractor_handles_ocr_spaces():
    rule = CustomFieldExtractionRule(
        field_id=3,
        extractor="receipt_total",
        normalize="monetary",
    )
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="E n d s u m m e  €       14.64",
        rules=[rule],
    )
    assert result is not None
    assert result.value == "14,64"


def test_regex_flags_accept_compact_im():
    rule = CustomFieldExtractionRule(
        field_id=3,
        patterns=[r"^endsumme\s*€?\s*([0-9]+[,.][0-9]{2})"],
        flags=["im"],
        normalize="monetary",
    )
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="Vorspann\nEndsumme € 14.64",
        rules=[rule],
    )
    assert result is not None
    assert result.value == "14,64"


def test_rule_source_can_use_title_instead_of_document_text():
    rule = CustomFieldExtractionRule(
        field_id=7,
        source="title",
        patterns=[r"Rechnung\s+([0-9]+)"],
        normalize="text",
    )
    result = extract_custom_field_value(
        field_id=7,
        field_name="Belegnummer",
        field_type="string",
        text="Dokumenttext ohne Nummer",
        rules=[rule],
        sources={"title": "Rechnung 4711"},
    )
    assert result is not None
    assert result.value == "4711"
