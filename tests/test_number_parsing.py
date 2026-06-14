from paperless_nc_import.validators import parse_number


def test_parse_number_accepts_decimal_comma():
    assert parse_number("14,64") == 14.64


def test_parse_number_accepts_decimal_dot_from_ocr():
    assert parse_number("14.64") == 14.64


def test_parse_number_accepts_german_thousands_and_decimal():
    assert parse_number("1.234,56") == 1234.56


def test_parse_number_accepts_english_thousands_and_decimal():
    assert parse_number("1,234.56") == 1234.56


def test_parse_number_preserves_old_single_thousands_dot_behavior():
    assert parse_number("1.234") == 1234.0
