from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._hashes: set[str] | None = None

    def _load(self) -> set[str]:
        hashes: set[str] = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sha = obj.get("sha256")
                    if sha:
                        hashes.add(str(sha))
        return hashes

    @property
    def hashes(self) -> set[str]:
        if self._hashes is None:
            self._hashes = self._load()
        return self._hashes

    def contains(self, sha256: str) -> bool:
        return sha256 in self.hashes

    def add(self, *, sha256: str, file: Path, task_id: str = "", document_id: int | None = None) -> None:
        obj = {
            "created": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256,
            "file": str(file),
            "task_id": task_id,
            "document_id": document_id,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.hashes.add(sha256)
