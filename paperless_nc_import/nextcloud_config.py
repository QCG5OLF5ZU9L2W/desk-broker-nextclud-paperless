from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
import os
import re

from .config import NextcloudConfig, expand_path
from .models import NextcloudMount


def _norm_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _strip_value(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
        value = value[1:-1]
    return value.strip()


def _first_option(section: dict[str, str], *names: str) -> str:
    lower = {k.lower(): v for k, v in section.items()}
    for name in names:
        if name.lower() in lower and str(lower[name.lower()]).strip():
            return str(lower[name.lower()]).strip()
    for key, value in lower.items():
        for name in names:
            if name.lower() in key and str(value).strip():
                return str(value).strip()
    return ""


def _find_journal(local_root: Path) -> Path | None:
    if not local_root.exists():
        return None
    candidates = sorted(local_root.glob(".sync_*.db"))
    if candidates:
        return candidates[0]
    candidates = sorted(local_root.glob("**/.sync_*.db"))
    return candidates[0] if candidates else None


def _read_raw_kv(path: Path) -> dict[str, str]:
    """Read Nextcloud's Qt-style config as a flat key/value map.

    The desktop client commonly stores keys such as
    ``0\\Folders\\1\\localPath=/home/...`` in an INI-looking file. Python's
    ConfigParser can read the file, but treating each section semantically can
    miss those backslash-namespaced keys. The old Go prototype therefore used a
    flat scanner; v0.1.1 does the same here.
    """
    kv: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return kv
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        kv[key] = _strip_value(value)
    return kv


def _first_config_value(kv: dict[str, str], *keys: str) -> str:
    for wanted in keys:
        if not wanted:
            continue
        for key, value in kv.items():
            if key.lower() == wanted.lower() and str(value).strip():
                return str(value).strip()
    return ""


def _first_config_value_by_suffix(kv: dict[str, str], suffix: str) -> str:
    suffix_l = suffix.lower()
    for key, value in kv.items():
        if key.lower().endswith(suffix_l) and str(value).strip():
            return str(value).strip()
    return ""


def _key_prefix_before_last_backslash(key: str) -> str:
    idx = key.rfind("\\")
    if idx < 0:
        return ""
    return key[: idx + 1]


def _account_prefix_for_key(key: str) -> str:
    lower = key.lower()
    needle = "\\folders\\"
    idx = lower.find(needle)
    if idx > 0:
        return key[:idx]
    parts = key.split("\\")
    if len(parts) >= 2:
        return parts[0]
    return ""


def _clean_cloud_path(value: str) -> str:
    value = _strip_value(value) or "/"
    # Some Nextcloud client values are URL-ish or contain percent escaping.
    value = value.replace("\\", "/")
    value = re.sub(r"/+/", "/", value)
    if not value.startswith("/"):
        value = "/" + value
    # Keep root stable.
    if value != "/":
        value = value.rstrip("/")
    return value


def _detect_mounts_flat(path: Path, cfg: NextcloudConfig) -> list[NextcloudMount]:
    kv = _read_raw_kv(path)
    mounts: list[NextcloudMount] = []
    seen: set[Path] = set()

    for key, value in kv.items():
        if "localpath" not in key.lower():
            continue
        local_raw = _strip_value(value)
        if not local_raw:
            continue
        local = Path(os.path.expandvars(os.path.expanduser(local_raw))).resolve()
        if not local.exists() or local in seen:
            continue
        seen.add(local)

        folder_prefix = _key_prefix_before_last_backslash(key)
        account_prefix = _account_prefix_for_key(key)

        server = _first_config_value(
            kv,
            account_prefix + r"\url",
            account_prefix + r"\server",
            account_prefix + r"\serverUrl",
            "url",
            "server",
            "serverUrl",
        )
        if not server:
            server = _first_config_value_by_suffix(kv, r"\url")

        user = _first_config_value(
            kv,
            account_prefix + r"\user",
            account_prefix + r"\username",
            account_prefix + r"\dav_user",
            account_prefix + r"\davUser",
            account_prefix + r"\http_user",
            "user",
            "username",
        )

        remote = _first_config_value(
            kv,
            folder_prefix + "targetPath",
            folder_prefix + "remotePath",
            folder_prefix + "targetPathUrl",
            folder_prefix + "serverPath",
            folder_prefix + "journalPath",
        ) or "/"

        mounts.append(
            NextcloudMount(
                local_root=local,
                server_url=_norm_url(server or cfg.server_url),
                user=user or cfg.user,
                remote_root=_clean_cloud_path(remote),
                journal_path=_find_journal(local),
                account_name=account_prefix,
            )
        )

    mounts.sort(key=lambda m: len(str(m.local_root)), reverse=True)
    return mounts


def _detect_mounts_ini_sections(path: Path, cfg: NextcloudConfig) -> list[NextcloudMount]:
    """Fallback for more conventional INI section layouts."""
    parser = ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")

    accounts: list[dict[str, str]] = []
    folders: list[dict[str, str]] = []

    for section_name in parser.sections():
        values = {k: v for k, v in parser.items(section_name)}
        url = _norm_url(_first_option(values, "url", "server", "serverUrl", "davUrl"))
        user = _first_option(values, "user", "username", "displayName")
        if url:
            accounts.append({"section": section_name, "url": url, "user": user})

        local = _first_option(values, "localPath", "localpath", "path")
        has_localish_key = any("localpath" in k.lower() or k.lower() in {"path", "targetpath"} for k in values)
        if local and ("folder" in section_name.lower() or has_localish_key):
            remote = _first_option(values, "remotePath", "targetPath", "serverPath", "journalPath") or "/"
            folder_account = _first_option(values, "account", "accountName")
            folders.append({
                "section": section_name,
                "local": local,
                "remote": remote,
                "account": folder_account,
                "url": url,
                "user": user,
            })

    mounts: list[NextcloudMount] = []
    default_account = accounts[0] if accounts else {"url": cfg.server_url, "user": cfg.user, "section": ""}

    for folder in folders:
        local = Path(os.path.expandvars(os.path.expanduser(folder["local"]))).resolve()
        if not local.exists():
            continue
        account = default_account
        if folder.get("account"):
            needle = folder["account"].lower()
            for acc in accounts:
                if needle in acc.get("section", "").lower() or needle in acc.get("url", "").lower():
                    account = acc
                    break
        mounts.append(
            NextcloudMount(
                local_root=local,
                server_url=_norm_url(folder.get("url") or account.get("url") or cfg.server_url),
                user=folder.get("user") or account.get("user") or cfg.user,
                remote_root=_clean_cloud_path(folder.get("remote") or "/"),
                journal_path=_find_journal(local),
                account_name=account.get("section", ""),
            )
        )
    mounts.sort(key=lambda m: len(str(m.local_root)), reverse=True)
    return mounts


def read_nextcloud_mounts(cfg: NextcloudConfig) -> list[NextcloudMount]:
    path = expand_path(cfg.config_path)
    if not path.exists():
        return []

    # Primary parser: Qt/backslash namespaced Nextcloud Desktop config.
    mounts = _detect_mounts_flat(path, cfg)

    # Fallback parser: conventional section-based INI variants.
    if not mounts:
        mounts = _detect_mounts_ini_sections(path, cfg)

    dedup: dict[Path, NextcloudMount] = {}
    for mount in mounts:
        dedup[mount.local_root] = mount
    result = list(dedup.values())
    result.sort(key=lambda m: len(str(m.local_root)), reverse=True)
    return result
