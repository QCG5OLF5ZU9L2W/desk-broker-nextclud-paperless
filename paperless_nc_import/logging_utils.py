from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
import sys


@dataclass
class StartupProfiler:
    enabled: bool = False
    stream: object = sys.stderr
    start: float = field(default_factory=perf_counter)
    last: float = field(default_factory=perf_counter)
    lines: list[str] = field(default_factory=list)

    def mark(self, label: str) -> None:
        now = perf_counter()
        delta = now - self.last
        total = now - self.start
        self.last = now
        line = f"{label:<68} Δ {delta:8.3f}s  Σ {total:8.3f}s"
        self.lines.append(line)
        if self.enabled:
            print(line, file=self.stream, flush=True)

    def text(self) -> str:
        return "\n".join(self.lines)


class AppLogger:
    def __init__(self, startup: StartupProfiler | None = None) -> None:
        self.messages: list[str] = []
        self.startup = startup or StartupProfiler(False)

    def info(self, message: str) -> None:
        self.messages.append(message)
        print(message, file=sys.stderr)

    def warn(self, message: str) -> None:
        self.info(f"WARNUNG: {message}")

    def error(self, message: str) -> None:
        self.info(f"FEHLER: {message}")

    def mark(self, label: str) -> None:
        self.startup.mark(label)
        self.messages.append(label)

    def text(self) -> str:
        parts = []
        if self.startup.lines:
            parts.append("Startprofil:\n" + self.startup.text())
        if self.messages:
            parts.append("Log:\n" + "\n".join(self.messages))
        return "\n\n".join(parts)
