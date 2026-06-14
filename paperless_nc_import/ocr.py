from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import shutil
import subprocess

from .config import OcrConfig
from .fs_utils import sha256_file


@dataclass(slots=True)
class OcrResult:
    input_path: Path
    upload_path: Path
    output_pdf: Path | None = None
    sidecar_txt: Path | None = None
    used_ocr: bool = False
    cache_hit: bool = False
    text_before_chars: int = 0
    text_after_chars: int = 0
    reason: str = ""
    engine: str = ""
    command: list[str] = field(default_factory=list)
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    assist_json: Path | None = None

    @property
    def sidecar_text(self) -> str:
        if self.sidecar_txt and self.sidecar_txt.exists():
            return self.sidecar_txt.read_text(encoding="utf-8", errors="replace")
        return ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "input_path": str(self.input_path),
            "upload_path": str(self.upload_path),
            "output_pdf": str(self.output_pdf) if self.output_pdf else "",
            "sidecar_txt": str(self.sidecar_txt) if self.sidecar_txt else "",
            "used_ocr": self.used_ocr,
            "cache_hit": self.cache_hit,
            "text_before_chars": self.text_before_chars,
            "text_after_chars": self.text_after_chars,
            "reason": self.reason,
            "engine": self.engine,
            "command": self.command,
            "return_code": self.return_code,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-4000:],
            "assist_json": str(self.assist_json) if self.assist_json else "",
        }


class OcrError(RuntimeError):
    pass


class OcrProcessor:
    """Local OCR pre-processing for scanned PDFs.

    v0.6 deliberately keeps archive OCR and import-assist OCR separate.  The
    implemented archive path is OCRmyPDF/Tesseract because it creates a proper
    searchable PDF that Paperless can ingest.  Assist engines such as PaddleOCR
    are represented in configuration, but are not required for the standard
    import path yet.
    """

    def __init__(self, cfg: OcrConfig) -> None:
        self.cfg = cfg
        self.cache_dir = Path(cfg.cache_dir).expanduser()

    @staticmethod
    def _chars(text: str) -> int:
        return sum(1 for c in text if not c.isspace())

    def available(self) -> tuple[bool, list[str]]:
        missing: list[str] = []
        for exe in ("ocrmypdf", "tesseract", "pdftotext"):
            if not shutil.which(exe):
                missing.append(exe)
        # OCRmyPDF depends on qpdf/Ghostscript for normal PDF/PDF-A output.
        if not shutil.which("qpdf"):
            missing.append("qpdf")
        if not shutil.which("gs"):
            missing.append("ghostscript(gs)")
        if self.cfg.clean and not shutil.which("unpaper"):
            missing.append("unpaper")
        return (not missing, missing)

    def extract_text(self, pdf: Path, *, max_pages: int | None = None) -> str:
        if not shutil.which("pdftotext"):
            return ""
        args = ["pdftotext", "-layout"]
        if max_pages and max_pages > 0:
            args.extend(["-f", "1", "-l", str(max_pages)])
        args.extend([str(pdf), "-"])
        try:
            proc = subprocess.run(args, text=True, capture_output=True, timeout=45, check=False)
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout or ""

    def has_text_layer(self, pdf: Path) -> tuple[bool, int]:
        text = self.extract_text(pdf, max_pages=self.cfg.text_probe_pages)
        count = self._chars(text)
        return count >= self.cfg.min_text_chars, count

    def _cache_paths(self, pdf: Path, sha256: str) -> tuple[Path, Path, Path, Path]:
        # Include important OCR settings in the cache key so stale OCR results are
        # not silently reused after language/mode/preprocess changes.
        key_data = {
            "sha256": sha256,
            "languages": self.cfg.languages,
            "mode": self.cfg.mode,
            "output_type": self.cfg.output_type,
            "rotate_pages": self.cfg.rotate_pages,
            "deskew": self.cfg.deskew,
            "clean": self.cfg.clean,
        }
        import hashlib

        key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        root = self.cache_dir / key
        root.mkdir(parents=True, exist_ok=True)
        stem = pdf.stem
        return root, root / f"{stem}.ocr.pdf", root / f"{stem}.ocr.txt", root / "ocr-result.json"

    def prepare(
        self,
        pdf: Path,
        *,
        sha256: str | None = None,
        force: bool = False,
        progress: Callable[[str, int], None] | None = None,
    ) -> OcrResult:
        pdf = Path(pdf).resolve()

        def report(message: str, percent: int) -> None:
            if progress:
                try:
                    progress(message, max(0, min(100, int(percent))))
                except Exception:
                    pass

        report("OCR: Vorbereitung", 1)
        if not self.cfg.enabled or self.cfg.mode == "never":
            report("OCR: deaktiviert", 100)
            return OcrResult(input_path=pdf, upload_path=pdf, reason="OCR deaktiviert")
        if self.cfg.archive_engine != "ocrmypdf":
            report("OCR: Archiv-Engine nicht implementiert", 100)
            return OcrResult(
                input_path=pdf,
                upload_path=pdf,
                reason=f"Archiv-OCR-Engine {self.cfg.archive_engine!r} ist in v0.6 nicht implementiert",
            )

        report("OCR: prüfe Programme", 3)
        ok, missing = self.available()
        if not ok:
            raise OcrError("OCR-Anforderungen fehlen: " + ", ".join(missing))

        report("OCR: prüfe vorhandene Textschicht", 8)
        has_text, before_chars = self.has_text_layer(pdf)
        mode = "force" if force else self.cfg.mode
        if mode == "auto" and has_text:
            report(f"OCR: Textschicht vorhanden ({before_chars} Zeichen), übersprungen", 100)
            return OcrResult(
                input_path=pdf,
                upload_path=pdf,
                text_before_chars=before_chars,
                text_after_chars=before_chars,
                reason="Textschicht vorhanden; OCR übersprungen",
            )

        report("OCR: berechne/prüfe Cache", 18)
        file_hash = sha256 or sha256_file(pdf)
        root, out_pdf, sidecar, meta = self._cache_paths(pdf, file_hash)
        if out_pdf.exists() and sidecar.exists() and not force:
            report("OCR: Cache-Treffer", 100)
            after_text = sidecar.read_text(encoding="utf-8", errors="replace")
            return OcrResult(
                input_path=pdf,
                upload_path=out_pdf if self.cfg.upload == "ocr_pdf" else pdf,
                output_pdf=out_pdf,
                sidecar_txt=sidecar,
                used_ocr=True,
                cache_hit=True,
                text_before_chars=before_chars,
                text_after_chars=self._chars(after_text),
                reason="OCR-Cache verwendet",
                engine="ocrmypdf",
            )

        report("OCR: starte OCRmyPDF/Tesseract", 25)
        lang = "+".join(self.cfg.languages or ["deu", "eng"])
        cmd = ["ocrmypdf", "--language", lang]
        if self.cfg.output_type:
            cmd.extend(["--output-type", self.cfg.output_type])
        if self.cfg.jobs and self.cfg.jobs > 0:
            cmd.extend(["--jobs", str(self.cfg.jobs)])
        if self.cfg.rotate_pages:
            cmd.append("--rotate-pages")
        if self.cfg.deskew:
            cmd.append("--deskew")
        if self.cfg.clean:
            cmd.append("--clean")
        if self.cfg.sidecar_text:
            cmd.extend(["--sidecar", str(sidecar)])

        if mode == "force":
            cmd.append("--force-ocr")
        elif mode == "redo":
            cmd.append("--redo-ocr")
        else:
            cmd.append("--skip-text")

        cmd.extend([str(pdf), str(out_pdf)])
        started = datetime.now(timezone.utc).isoformat()
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                # OCRmyPDF writes useful status/progress output mostly to stderr.
                # The exact progress format is not stable, so the GUI receives
                # staged progress plus the latest OCRmyPDF line.
                import threading

                def read_stdout() -> None:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        stdout_chunks.append(line)

                th = threading.Thread(target=read_stdout, daemon=True)
                th.start()
                assert proc.stderr is not None
                last_percent = 25
                for line in proc.stderr:
                    stderr_chunks.append(line)
                    clean = line.strip().replace("\r", " ")
                    if clean:
                        if last_percent < 90:
                            last_percent += 1
                        report("OCR: " + clean[-160:], last_percent)
                rc = proc.wait(timeout=self.cfg.timeout_seconds if self.cfg.timeout_seconds > 0 else None)
                th.join(timeout=1)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                raise OcrError(f"OCR-Timeout nach {self.cfg.timeout_seconds}s: {exc}") from exc
        except OcrError:
            raise
        except Exception as exc:
            raise OcrError(f"OCRmyPDF konnte nicht gestartet werden: {exc}") from exc

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        report("OCR: OCRmyPDF beendet, prüfe Ergebnis", 92)
        if rc != 0:
            # OCRmyPDF returns specific non-zero codes for some recoverable cases,
            # but for the importer a missing output PDF is never useful.
            if not out_pdf.exists():
                raise OcrError(
                    "OCRmyPDF fehlgeschlagen "
                    f"(Exit {rc}). stderr:\n{stderr[-2000:]}"
                )

        report("OCR: erstelle/lese Text-Sidecar", 95)
        if not sidecar.exists() and out_pdf.exists():
            sidecar.write_text(self.extract_text(out_pdf), encoding="utf-8")
        after_text = sidecar.read_text(encoding="utf-8", errors="replace") if sidecar.exists() else ""
        result = OcrResult(
            input_path=pdf,
            upload_path=out_pdf if self.cfg.upload == "ocr_pdf" else pdf,
            output_pdf=out_pdf if out_pdf.exists() else None,
            sidecar_txt=sidecar if sidecar.exists() else None,
            used_ocr=out_pdf.exists(),
            cache_hit=False,
            text_before_chars=before_chars,
            text_after_chars=self._chars(after_text),
            reason="OCR erzeugt" if out_pdf.exists() else "OCR ohne Ausgabedatei beendet",
            engine="ocrmypdf",
            command=cmd,
            return_code=rc,
            stdout=stdout,
            stderr=stderr,
        )
        report("OCR: fertig", 100)
        meta.write_text(
            json.dumps(
                {
                    "created": started,
                    "result": result.to_payload(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return result
