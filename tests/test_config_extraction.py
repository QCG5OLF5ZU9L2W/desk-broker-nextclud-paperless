from paperless_nc_import.config import load_config


def test_config_loads_custom_field_extraction_rules_and_alias_ids(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
custom:
  custom_field_nextcloud_path_id: "14"
  custom_field_local_path_id: ""
  custom_field_extraction_rules:
    - field_id: "3"
      field_name: Rechnungsbetrag
      field_type: monetary
      extractor: receipt_total
      normalize: monetary
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.custom.field_nextcloud_cloud_path_id == 14
    assert cfg.custom.field_local_path_id is None
    assert len(cfg.custom.custom_field_extraction_rules) == 1
    rule = cfg.custom.custom_field_extraction_rules[0]
    assert rule.field_id == 3
    assert rule.field_name == "Rechnungsbetrag"
    assert rule.extractor == "receipt_total"
