#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any


def _fail(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def _sha_for_path(path: Path, dpi: int, max_pages: int) -> str:
    st = path.stat()
    payload = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{dpi}|{max_pages}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _render_pdf_pages(pdf: Path, workdir: Path, dpi: int, max_pages: int) -> list[Path]:
    if not shutil.which("pdftoppm"):
        _fail("pdftoppm fehlt. Installiere poppler-utils.")
    pages: list[Path] = []
    for page_no in range(1, max_pages + 1):
        prefix = workdir / f"page-{page_no}"
        cmd = ["pdftoppm", "-f", str(page_no), "-l", str(page_no), "-singlefile", "-r", str(dpi), "-png", str(pdf), str(prefix)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        img = prefix.with_suffix(".png")
        if proc.returncode != 0 or not img.exists():
            if page_no == 1:
                _fail(f"pdftoppm konnte Seite 1 nicht rendern: {proc.stderr.strip()}")
            break
        pages.append(img)
    return pages


def _normalize_text(text: str) -> str:
    text = (text or "").strip().replace("€", " EUR ")
    text = re.sub(r"\s+", " ", text)
    # OCR-Schäden rund um Geldbeträge normalisieren.
    text = re.sub(r"(?<!\d)[\.,](\d{1,5})[,.](\d{2})(?!\d)", r"\1,\2", text)
    text = re.sub(r"(?<!\d)[\.,]+(\d{1,5},\d{2})(?!\d)", r"\1", text)
    text = re.sub(r"(\d+)\.,(\d{2})", r"\1,\2", text)
    text = re.sub(r"(\d+),\.(\d{2})", r"\1,\2", text)
    text = re.sub(r"(?<!\d)(\d{1,5})\.(\d{2})(?!\d)", r"\1,\2", text)
    text = re.sub(r"(?i)\b[a-z]{1,5}(\d{1,5},\d{2}\s*EUR\b)", r"\1", text)
    return text.strip()


def _box_xywh(box: Any) -> tuple[float, float, float, float]:
    if not box:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(x, (int, float)) for x in box):
        x1, y1, x2, y2 = [float(x) for x in box]
        return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)
    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


@dataclass
class OCRRecord:
    text: str
    score: float | None
    box: Any
    page: int

    @property
    def x(self) -> float:
        return _box_xywh(self.box)[0]

    @property
    def y(self) -> float:
        return _box_xywh(self.box)[1]

    @property
    def w(self) -> float:
        return _box_xywh(self.box)[2]

    @property
    def h(self) -> float:
        return _box_xywh(self.box)[3]

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "score": self.score, "box": self.box, "page": self.page}


def _extract_records_from_result(result: Any, page_no: int) -> list[OCRRecord]:
    records: list[OCRRecord] = []
    pages = result if isinstance(result, list) else [result]
    for page in pages:
        if page is None:
            continue
        raw = getattr(page, "res", None)
        if isinstance(raw, dict):
            texts = raw.get("rec_texts") or []
            scores = raw.get("rec_scores") or []
            boxes = raw.get("rec_boxes") or raw.get("rec_polys") or []
            for i, text in enumerate(texts):
                box = boxes[i] if i < len(boxes) else None
                if hasattr(box, "tolist"):
                    box = box.tolist()
                score = float(scores[i]) if i < len(scores) else None
                records.append(OCRRecord(_normalize_text(str(text)), score, box, page_no))
            continue
        items = page
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], list):
            maybe_nested = items[0]
            if maybe_nested and isinstance(maybe_nested[0], list) and len(maybe_nested[0]) >= 2:
                items = maybe_nested
        if isinstance(items, list):
            for item in items:
                try:
                    records.append(OCRRecord(_normalize_text(str(item[1][0])), float(item[1][1]), item[0], page_no))
                except Exception:
                    pass
    return [r for r in records if r.text]


def _build_ocr():
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    from paddleocr import PaddleOCR
    attempts = [
        {"lang": "german", "use_angle_cls": True, "use_gpu": False, "show_log": False, "use_mkldnn": False},
        {"lang": "german", "use_angle_cls": False, "use_gpu": False, "show_log": False, "use_mkldnn": False},
        {"lang": "en", "use_angle_cls": True, "use_gpu": False, "show_log": False, "use_mkldnn": False},
    ]
    last: Exception | None = None
    for kwargs in attempts:
        try:
            return PaddleOCR(**kwargs)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"PaddleOCR konnte nicht initialisiert werden: {last}")


def records_to_layout_text(records: list[OCRRecord], min_score: float = 0.50) -> str:
    usable = [r for r in records if r.text and (r.score is None or r.score >= min_score)]
    if not usable:
        return ""
    output_lines: list[str] = []
    for page in sorted(set(r.page for r in usable)):
        page_records = sorted([r for r in usable if r.page == page], key=lambda r: (r.cy, r.x))
        heights = [max(8.0, r.h) for r in page_records if r.h > 0]
        row_threshold = max(18.0, median(heights) * 0.65) if heights else 24.0
        rows: list[list[OCRRecord]] = []
        for rec in page_records:
            for row in rows:
                if abs(rec.cy - median([x.cy for x in row])) <= row_threshold:
                    row.append(rec)
                    break
            else:
                rows.append([rec])
        rows.sort(key=lambda row: median([r.cy for r in row]))
        if len(set(r.page for r in usable)) > 1:
            output_lines.append(f"--- page {page} ---")
        for row in rows:
            row.sort(key=lambda r: r.x)
            # Tests und Sidecar-JSON können OCRRecord-Instanzen enthalten, deren
            # Text noch nicht normalisiert wurde. Deshalb wird hier beim
            # geometrischen Zusammenbau erneut normalisiert. Das repariert u.a.
            # OCR-Artefakte wie `.23,09` und `23.09` zu `23,09`.
            parts = [_normalize_text(r.text) for r in row if r.text]
            line = re.sub(r"\s+", " ", "  ".join(parts)).strip()
            line = _normalize_text(line)
            if line:
                output_lines.append(line)
    return "\n".join(output_lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.50)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    src = Path(args.input).expanduser()
    out = Path(args.output).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        _fail(f"Eingabedatei fehlt: {src}")
    cache_key = _sha_for_path(src, args.dpi, args.max_pages)
    json_path = out / f"{cache_key}.paddleocr.json"
    txt_path = out / f"{cache_key}.paddleocr.txt"
    if json_path.exists() and txt_path.exists() and not args.force:
        print(json.dumps({"json": str(json_path), "text": str(txt_path), "cached": True}, ensure_ascii=False))
        return
    with tempfile.TemporaryDirectory(prefix="desk-broker-paddleocr-") as tmp:
        tmpdir = Path(tmp)
        images = _render_pdf_pages(src, tmpdir, args.dpi, args.max_pages) if src.suffix.lower() == ".pdf" else [src]
        if not images:
            _fail("Keine OCR-Bilder erzeugt.")
        ocr = _build_ocr()
        records: list[OCRRecord] = []
        for idx, image in enumerate(images, start=1):
            result = ocr.ocr(str(image), cls=True)
            records.extend(_extract_records_from_result(result, idx))
    layout_text = records_to_layout_text(records, min_score=args.min_score)
    json_path.write_text(json.dumps({"input": str(src), "dpi": args.dpi, "max_pages": args.max_pages, "records": [r.as_dict() for r in records], "layout_text": layout_text}, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(layout_text, encoding="utf-8")
    print(json.dumps({"json": str(json_path), "text": str(txt_path), "cached": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
