from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .models import NextcloudMount, NextcloudReference
from .nextcloud_journal import lookup_journal


def _join_cloud(root: str, rel: str) -> str:
    root = root or "/"
    if not root.startswith("/"):
        root = "/" + root
    if not root.endswith("/"):
        root += "/"
    out = root + rel.lstrip("/")
    if not out.startswith("/"):
        out = "/" + out
    return out.replace("//", "/")


def _quote_path(path: str) -> str:
    return "/".join(quote(part) for part in path.strip("/").split("/") if part)


def best_mount(path: Path, mounts: list[NextcloudMount]) -> NextcloudMount | None:
    candidates = [m for m in mounts if m.contains(path)]
    if not candidates:
        return None
    candidates.sort(key=lambda m: len(str(m.local_root)), reverse=True)
    return candidates[0]


def build_nextcloud_reference(path: Path, mounts: list[NextcloudMount]) -> NextcloudReference:
    mount = best_mount(path, mounts)
    if not mount:
        return NextcloudReference(mount=None, local_path=path, status="Datei liegt in keiner erkannten Nextcloud-Sync-Wurzel")
    rel = path.resolve().relative_to(mount.local_root.resolve()).as_posix()
    cloud_path = _join_cloud(mount.remote_root, rel)
    server = mount.server_url.rstrip("/")
    dirname = "/" + "/".join(cloud_path.strip("/").split("/")[:-1]) if "/" in cloud_path.strip("/") else "/"
    filename = Path(cloud_path).name
    web_link = f"{server}/apps/files/files?dir={quote(dirname)}&scrollto={quote(filename)}"
    webdav = ""
    if mount.user:
        webdav = f"{server}/remote.php/dav/files/{quote(mount.user)}/{_quote_path(cloud_path)}"
    journal_data = lookup_journal(mount.journal_path, cloud_path)
    file_id = journal_data.get("file_id", "")
    internal = f"{server}/f/{quote(file_id)}" if file_id else ""
    status = "Nextcloud FileID aus Client-Journal gefunden." if file_id else "Cloud-Pfad aus Nextcloud-Client-Konfiguration berechnet; FileID nicht im Journal gefunden."
    return NextcloudReference(
        mount=mount,
        local_path=path,
        cloud_path=cloud_path,
        web_link=web_link,
        internal_link=internal,
        webdav_url=webdav,
        file_id=file_id,
        oc_id=journal_data.get("oc_id", ""),
        etag=journal_data.get("etag", ""),
        journal_path=mount.journal_path,
        status=status,
    )
