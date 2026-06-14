from paperless_nc_import.community_learning import build_community_signal, is_safe_label, unsafe_label_reason


def test_safe_community_signal_contains_no_value():
    signal = build_community_signal(
        label="Fahrzeugpreis inklusive Nebenkosten",
        field_role="amount.total",
        field_type="monetary",
        extractor="label_before_value",
        result="accepted",
        app_version="0.7.7",
    )
    assert signal is not None
    payload = signal.to_payload()
    assert payload == {
        "schema": 1,
        "locale": "de",
        "field_role": "amount.total",
        "field_type": "monetary",
        "extractor": "label_before_value",
        "label_normalized": "fahrzeugpreis inklusive nebenkosten",
        "result": "accepted",
        "app_version": "0.7.7",
    }
    assert "15900" not in repr(payload)


def test_community_signal_rejects_digits_and_values():
    assert not is_safe_label("Fahrzeugpreis 15900,00")
    assert unsafe_label_reason("Fahrzeugpreis 15900,00") == "digit"
    assert build_community_signal(
        label="Fahrzeugpreis 15900,00",
        field_role="amount.total",
        field_type="monetary",
        extractor="label_before_value",
        result="accepted",
    ) is None


def test_community_signal_rejects_iban_like_label():
    assert not is_safe_label("IBAN DE49 8005 3000 1131 0425 29")
