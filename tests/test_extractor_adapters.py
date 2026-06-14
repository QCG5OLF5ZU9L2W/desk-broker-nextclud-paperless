from paperless_nc_import.extraction import extract_custom_field_value
from paperless_nc_import.extractors.normalizers import iban_mod97_valid, normalize_date, normalize_money


def test_generic_amount_total_uses_semantic_label_not_supplier_text():
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="Rechnung\nRechnungsbetrag: 1.234,56 EUR\nVielen Dank.",
        rules=[],
        field_role="amount.total",
    )
    assert result is not None
    assert result.value == "1234,56"
    assert result.role == "amount.total"
    assert result.label_normalized == "rechnungsbetrag"


def test_generic_amount_total_rejects_unit_price_and_uses_total_label():
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="""
Artikel A                 0,88 x 12        10,56
Artikel B                 3,69 x 2          7,38
Pfandrueckgabe                              -1,50
-------------------------------------------------
zu zahlen                                  23,09
Kreditkarte                                23,09
""",
        rules=[],
        field_role="amount.total",
    )
    assert result is not None
    assert result.value == "23,09"
    assert result.label_normalized == "zu zahlen"


def test_generic_amount_total_does_not_guess_from_item_rows_without_total_context():
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="Artikel A 0,88 x 12 10,56\nArtikel B 3,69 x 2 7,38",
        rules=[],
        field_role="amount.total",
    )
    assert result is None


def test_generic_amount_total_ignores_percentage_tax_table():
    result = extract_custom_field_value(
        field_id=3,
        field_name="Rechnungsbetrag",
        field_type="monetary",
        text="MwSt Netto Steuer Brutto\n19,00% 100,00 19,00 119,00",
        rules=[],
        field_role="amount.total",
    )
    assert result is None


def test_generic_invoice_date_extraction():
    result = extract_custom_field_value(
        field_id=20,
        field_name="Belegdatum",
        field_type="date",
        text="Rechnungsdatum: 14.06.2026\nFällig am: 30.06.2026",
        rules=[],
        field_role="date.invoice",
    )
    assert result is not None
    assert result.value == "2026-06-14"
    assert result.role == "date.invoice"


def test_generic_due_date_extraction():
    result = extract_custom_field_value(
        field_id=21,
        field_name="Faelligkeit",
        field_type="date",
        text="Rechnungsdatum: 14.06.2026\nFällig am: 30.06.2026",
        rules=[],
        field_role="date.due",
    )
    assert result is not None
    assert result.value == "2026-06-30"
    assert result.role == "date.due"


def test_generic_iban_extraction_validates_checksum():
    result = extract_custom_field_value(
        field_id=6,
        field_name="IBAN",
        field_type="string",
        text="Bitte überweisen Sie an IBAN DE89 3704 0044 0532 0130 00.",
        rules=[],
        field_role="bank.iban",
    )
    assert result is not None
    assert result.value == "DE89370400440532013000"
    assert result.role == "bank.iban"


def test_normalizers_are_deterministic_without_optional_dependencies():
    assert normalize_money("1.234,56 €") == "1234,56"
    assert normalize_date("14.06.2026") == "2026-06-14"
    assert iban_mod97_valid("DE89370400440532013000") is True
