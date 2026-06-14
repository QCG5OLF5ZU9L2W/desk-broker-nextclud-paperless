from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import sys

from .config import default_config_path, load_config
from .fs_utils import collect_input_files
from .importer import Importer
from .logging_utils import AppLogger, StartupProfiler
from .nextcloud_config import read_nextcloud_mounts
from .ocr import OcrProcessor
from .paperless_client import PaperlessClient, PaperlessError


def build_parser() -> ArgumentParser:
    p = ArgumentParser(prog="paperless-nc-import")
    p.add_argument("files", nargs="*", help="Dateien oder Ordner. Ohne Argumente wird import.inbox_dir gescannt.")
    p.add_argument("--config", default=str(default_config_path()), help="Pfad zur YAML-Konfiguration")
    p.add_argument("--gui", action="store_true", help="GUI öffnen")
    p.add_argument("--no-gui", action="store_true", help="Headless importieren")
    p.add_argument("--dry-run", action="store_true", help="Nichts ändern und nichts hochladen")
    p.add_argument("--doctor", action="store_true", help="Konfiguration, Paperless und Nextcloud prüfen")
    p.add_argument("--startup-log", action="store_true", help="Startprofil ins Terminal schreiben")
    p.add_argument("--no-cache", action="store_true", help="Paperless-Metadaten nicht aus Cache laden")
    p.add_argument("--ocr-never", action="store_true", help="OCR für diesen Lauf deaktivieren")
    p.add_argument("--ocr-force", action="store_true", help="OCR für diesen Lauf erzwingen")
    return p


def doctor(cfg, logger: AppLogger, no_cache: bool = False) -> int:
    logger.info(f"Konfiguration: {cfg.path}")
    logger.info("[OK] config.yaml lesbar")
    if cfg.paperless.url:
        logger.info("[OK] Paperless URL gesetzt")
    else:
        logger.error("Paperless URL fehlt")
        return 1
    if cfg.paperless.token:
        logger.info("[OK] Paperless Token gesetzt")
    else:
        logger.error("Paperless Token fehlt")
        return 1
    try:
        client = PaperlessClient(cfg.paperless)
        metadata = client.load_metadata(use_cache=not no_cache)
        source = "Cache" if metadata.from_cache else "API"
        logger.info(f"[OK] Paperless Metadaten ({source}): {len(metadata.tags)} Tags, {len(metadata.correspondents)} Korrespondenten, {len(metadata.document_types)} Dokumenttypen, {len(metadata.storage_paths)} Storage Paths, {len(metadata.custom_fields)} Custom Fields")
    except Exception as exc:
        logger.error(f"Paperless API nicht nutzbar: {exc}")
        return 1
    if cfg.import_.inbox_dir.exists():
        logger.info(f"[OK] Inbox vorhanden: {cfg.import_.inbox_dir}")
    else:
        logger.warn(f"Inbox nicht vorhanden: {cfg.import_.inbox_dir}")
    try:
        cfg.import_.state_file.parent.mkdir(parents=True, exist_ok=True)
        probe = cfg.import_.state_file.parent / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        logger.info("[OK] State-Verzeichnis beschreibbar")
    except Exception as exc:
        logger.error(f"State-Verzeichnis nicht beschreibbar: {exc}")
        return 1
    mounts = read_nextcloud_mounts(cfg.nextcloud)
    if mounts:
        logger.info("[OK] Nextcloud lokale Sync-Wurzeln")
        for mount in mounts:
            logger.info(f"  - {mount.local_root} -> {mount.server_url} | remote {mount.remote_root} | user {mount.user} | journal {'✓' if mount.journal_path else '—'}")
    else:
        logger.warn("Keine Nextcloud-Sync-Wurzel erkannt")

    if cfg.deck.enabled:
        logger.info("[OK] Deck-Integration aktiviert; Nextcloud-Ziel wird pro Datei aus dem erkannten Sync-Pfad bestimmt")
        logger.info(f"[OK] Deck-Secrets-Datei: {cfg.deck.secrets_file} ({'vorhanden' if cfg.deck.secrets_file.exists() else 'nicht vorhanden'})")
        if cfg.deck.routes:
            from pathlib import Path
            import os
            for route in cfg.deck.routes:
                where = route.match_local_root or route.match_server or route.match_user or "<Fallback/alle erkannten Mounts>"
                if route.match_local_root:
                    where = str(Path(os.path.expandvars(os.path.expanduser(route.match_local_root))).resolve(strict=False))
                auth = route.username or "<Mount-User>"
                pw = "env:" + route.app_password_env if route.app_password_env else ("gesetzt" if route.app_password else "FEHLT")
                if route.app_password_env and not os.environ.get(route.app_password_env):
                    pw += " (nicht gesetzt)"
                logger.info(f"  - Route {route.name or 'ohne Namen'}: match={where} user={auth} board={route.board_id} stack={route.stack_id} password={pw}")
        else:
            logger.warn("Deck ist aktiviert, aber es sind keine deck.routes konfiguriert")
    else:
        logger.info("Deck-Integration ist deaktiviert")

    try:
        ocr = OcrProcessor(cfg.ocr)
        ok, missing = ocr.available()
        if cfg.ocr.enabled and cfg.ocr.mode != "never":
            if ok:
                logger.info("[OK] OCR-Anforderungen gefunden: ocrmypdf, tesseract, pdftotext")
                logger.info(f"[OK] OCR-Konfiguration: mode={cfg.ocr.mode} languages={'+'.join(cfg.ocr.languages)} upload={cfg.ocr.upload} cache={cfg.ocr.cache_dir}")
            else:
                logger.warn("OCR-Anforderungen fehlen: " + ", ".join(missing))
        else:
            logger.info("OCR ist deaktiviert")
    except Exception as exc:
        logger.warn(f"OCR-Prüfung fehlgeschlagen: {exc}")
    return 0


def headless_import(cfg, logger: AppLogger, files: list[str], *, dry_run: bool, no_cache: bool) -> int:
    client = PaperlessClient(cfg.paperless)
    logger.mark("Paperless-Client erstellt")
    metadata = client.load_metadata(use_cache=not no_cache)
    logger.mark(f"Paperless-Metadaten geladen: {len(metadata.tags)} Tags, {len(metadata.correspondents)} Korrespondenten, {len(metadata.custom_fields)} Custom Fields")
    mounts = read_nextcloud_mounts(cfg.nextcloud)
    logger.mark(f"Nextcloud-Client-Konfiguration gelesen: {len(mounts)} Sync-Wurzeln")
    paths = collect_input_files(files, cfg.import_.inbox_dir, cfg.import_.pattern, cfg.import_.min_age_seconds)
    if not paths:
        if files:
            logger.warn("Keine Eingabedateien gefunden; übergebene Pfade existieren nicht oder enthalten keine passenden Dateien: " + ", ".join(files))
        else:
            logger.warn(f"Keine Eingabedateien gefunden; gescannt: {cfg.import_.inbox_dir} Muster={cfg.import_.pattern} Mindestalter={cfg.import_.min_age_seconds}s")
        return 0
    importer = Importer(cfg, client)
    for path in paths:
        info = importer.build_file_info(path, mounts)
        selection = importer.default_selection(info, metadata)
        result = importer.import_one(info, selection, metadata, dry_run=dry_run)
        if dry_run:
            logger.info(f"DRY-RUN: {path} -> rename={result.renamed_to or '-'}")
        else:
            deck_info = f" deck={result.deck.card_id}" if getattr(result, "deck", None) and result.deck.card_id else ""
            logger.info(f"Import gestartet: {path} -> task={result.task_id} document={result.document_id or '-'}{deck_info}")
        for warning in result.warnings:
            logger.warn(warning)
    return 0


def run_gui(cfg, logger: AppLogger, files: list[str], *, dry_run: bool, no_cache: bool) -> int:
    try:
        from .gui.main_window import run_gui as run_qt_gui
    except Exception as exc:
        logger.error(f"GUI kann nicht geladen werden. Ist PySide6 installiert? {exc}")
        return 1
    return run_qt_gui(cfg, logger, files, dry_run=dry_run, no_cache=no_cache)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    startup = StartupProfiler(enabled=args.startup_log)
    logger = AppLogger(startup)
    try:
        cfg = load_config(Path(args.config))
    except Exception as exc:
        print(f"ABBRUCH: Konfiguration ist nicht lesbar: {exc}", file=sys.stderr)
        return 1
    logger.mark("Konfiguration geladen")
    if args.ocr_never:
        cfg.ocr.mode = "never"
    if args.ocr_force:
        cfg.ocr.mode = "force"

    if args.doctor:
        return doctor(cfg, logger, no_cache=args.no_cache)

    use_gui = args.gui or (cfg.gui.enabled and cfg.gui.auto_for_explicit_files and bool(args.files) and not args.no_gui)
    if use_gui and not args.no_gui:
        return run_gui(cfg, logger, args.files, dry_run=args.dry_run, no_cache=args.no_cache)
    try:
        return headless_import(cfg, logger, args.files, dry_run=args.dry_run, no_cache=args.no_cache)
    except PaperlessError as exc:
        logger.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
