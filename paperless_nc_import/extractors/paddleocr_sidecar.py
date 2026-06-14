from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from .base import ExtractorInput, ExtractorResult
from .generic_text import GenericTextExtractor


class PaddleOCRSidecarExtractor:
    name = "paddleocr_sidecar"
    priority = 70

    def extract(self, item: ExtractorInput) -> list[ExtractorResult]:
        cfg = _load_config(item.sources or {})
        if not cfg.get("enabled"):
            return []
        source_path = _source_path(item.sources or {})
        if not source_path:
            return []
        path = Path(source_path).expanduser()
        if not path.exists():
            return []
        try:
            current = GenericTextExtractor().extract(item)
            if any(float(getattr(m, "confidence", 0.0) or 0.0) >= 0.90 for m in current):
                return []
        except Exception:
            pass
        layout_text = _run_sidecar(path, cfg)
        if not layout_text.strip():
            return []
        sources = dict(item.sources or {})
        sources["paddleocr_layout_text"] = layout_text
        sources["paddleocr_enabled"] = True
        combined = (item.text or "").rstrip()
        if combined:
            combined += "\n\n--- paddleocr layout text ---\n"
        combined += layout_text.strip()
        return GenericTextExtractor().extract(replace(item, text=combined, sources=sources))


def _source_path(sources: dict[str, Any]) -> str | None:
    for key in ("path", "file_path", "pdf_path", "source_path", "local_path"):
        value = sources.get(key)
        if value:
            return str(value)
    return None


def _load_yaml_config() -> dict[str, Any]:
    cfg_path = Path(os.environ.get("PAPERLESS_NC_IMPORT_CONFIG", "~/.config/paperless-nc-import/config.yaml")).expanduser()
    if not cfg_path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_config(sources: dict[str, Any]) -> dict[str, Any]:
    source_cfg = sources.get("paddleocr") if isinstance(sources.get("paddleocr"), dict) else {}
    yaml_cfg = _load_yaml_config()
    paddle_cfg = yaml_cfg.get("ocr_backends", {}).get("paddleocr", {}) if isinstance(yaml_cfg.get("ocr_backends", {}), dict) else {}
    cfg: dict[str, Any] = {}
    cfg.update(paddle_cfg if isinstance(paddle_cfg, dict) else {})
    cfg.update(source_cfg)
    env_enabled = os.environ.get("PAPERLESS_NC_IMPORT_PADDLEOCR_ENABLED")
    if env_enabled is not None:
        cfg["enabled"] = env_enabled.lower() in ("1", "true", "yes", "on")
    if os.environ.get("PAPERLESS_NC_IMPORT_PADDLEOCR_PYTHON"):
        cfg["python"] = os.environ["PAPERLESS_NC_IMPORT_PADDLEOCR_PYTHON"]
    if os.environ.get("PAPERLESS_NC_IMPORT_PADDLEOCR_CACHE_DIR"):
        cfg["cache_dir"] = os.environ["PAPERLESS_NC_IMPORT_PADDLEOCR_CACHE_DIR"]
    cfg.setdefault("enabled", False)
    cfg.setdefault("python", "~/.local/share/paperless-nc-import/paddleocr-sidecar/.venv/bin/python")
    cfg.setdefault("cache_dir", "~/.cache/paperless-nc-import/paddleocr")
    cfg.setdefault("dpi", 300)
    cfg.setdefault("max_pages", 3)
    cfg.setdefault("min_score", 0.50)
    cfg.setdefault("timeout", 180)
    return cfg


def _run_sidecar(path: Path, cfg: dict[str, Any]) -> str:
    py = Path(str(cfg.get("python", ""))).expanduser()
    if not py.exists() or not os.access(py, os.X_OK):
        return ""
    cache_dir = Path(str(cfg.get("cache_dir", "~/.cache/paperless-nc-import/paddleocr"))).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).with_name("paddleocr_worker.py")
    cmd = [str(py), str(worker), "--input", str(path), "--output", str(cache_dir), "--dpi", str(int(cfg.get("dpi", 300))), "--max-pages", str(int(cfg.get("max_pages", 3))), "--min-score", str(float(cfg.get("min_score", 0.50)))]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=int(cfg.get("timeout", 180)), env={**os.environ, "FLAGS_use_mkldnn": "0", "FLAGS_enable_pir_api": "0"})
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    try:
        info = json.loads(proc.stdout.strip().splitlines()[-1])
        text_path = Path(info["text"])
        return text_path.read_text(encoding="utf-8", errors="ignore") if text_path.exists() else ""
    except Exception:
        return ""
