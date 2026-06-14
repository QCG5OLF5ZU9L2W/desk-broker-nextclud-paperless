from paperless_nc_import.validators import is_valid_iban


def test_valid_iban():
    assert is_valid_iban("DE89 3704 0044 0532 0130 00")


def test_invalid_iban():
    assert not is_valid_iban("DE89 3704 0044 0532 0130 01")
