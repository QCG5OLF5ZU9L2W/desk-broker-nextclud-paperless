from paperless_nc_import.analytics.duckdb_store import (
    AnalyticsDocumentRecord,
    DuckDBAnalyticsStore,
    SCHEMA_SQL,
    source_path_hash,
)


def test_duckdb_analytics_record_export_is_privacy_aware():
    store = DuckDBAnalyticsStore("~/dummy.duckdb")
    record = AnalyticsDocumentRecord(
        global_document_id="urn:paperless:example:document:1",
        paperless_document_id=1,
        amount_total=123.45,
        extractor="generic_text",
        confidence=0.91,
        source_path_hash=source_path_hash("/private/path/rechnung.pdf"),
        metadata={"role": "amount.total"},
    )
    exported = store.export_record_dict(record)
    assert "metadata" not in exported
    assert "metadata_json" in exported
    assert exported["source_path_hash"]
    assert "/private/path" not in str(exported)


def test_duckdb_schema_has_no_ocr_text_or_path_columns():
    lowered = SCHEMA_SQL.casefold()
    assert "ocr" not in lowered
    assert "fulltext" not in lowered
    assert "source_path_hash" in lowered
    assert "source_path text" not in lowered
