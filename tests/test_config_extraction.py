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


def test_config_loads_field_roles_for_extraction(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
extraction:
  enabled: true
  locale: de
  field_roles:
    "3": amount.total
    "19": amount.vat
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.extraction.enabled is True
    assert cfg.extraction.locale == "de"
    assert cfg.extraction.field_roles == {3: "amount.total", 19: "amount.vat"}


def test_config_loads_community_learning_consent_and_privacy_defaults(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
community_learning:
  enabled: true
  endpoint: "https://learning.example.test/api/v1/"
  consent:
    granted: true
    version: 1
    granted_at: "2026-06-14T10:00:00+02:00"
    method: gui
  mode:
    submit: queue_and_review
  privacy:
    send_values: false
    send_ocr_text: false
    send_paths: false
    send_document_ids: false
    send_installation_id: false
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.community_learning.enabled is True
    assert cfg.community_learning.endpoint == "https://learning.example.test/api/v1"
    assert cfg.community_learning.consent.granted is True
    assert cfg.community_learning.consent.method == "gui"
    assert cfg.community_learning.mode.submit == "queue_and_review"
    assert cfg.community_learning.privacy.send_values is False
