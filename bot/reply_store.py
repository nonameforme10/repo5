from __future__ import annotations

import json
from pathlib import Path


DEFAULT_WARNINGS = [
    "Huh? why are you here, get outta here, i only speak with reality",
    "i said get outta here",
    "ok do whatever you want",
]


class ReplyStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.warnings, self.ragebaits = self._load()

    def _load(self) -> tuple[list[str], list[str]]:
        if not self.path.exists():
            return DEFAULT_WARNINGS, []

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DEFAULT_WARNINGS, []

        if not isinstance(data, dict):
            return DEFAULT_WARNINGS, []

        warnings = self._valid_lines(data.get("warnings")) or DEFAULT_WARNINGS
        ragebaits = self._valid_lines(data.get("ragebaits"))
        return warnings, ragebaits

    @staticmethod
    def _valid_lines(value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        seen: set[str] = set()
        lines: list[str] = []
        for item in value:
            line = str(item or "").strip()
            if not line or line in seen:
                continue

            seen.add(line)
            lines.append(line)

        return lines

    def reply_for_count(self, count: int) -> str | None:
        lines = [*self.warnings, *self.ragebaits]
        if count < 0 or count >= len(lines):
            return None

        return lines[count]
