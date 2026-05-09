from __future__ import annotations

import json
from pathlib import Path


class TargetStore:
    def __init__(self, path: Path, fallback_chat_id: str = "") -> None:
        self.path = path
        self.fallback_chat_id = fallback_chat_id

    def get(self) -> str:
        if not self.path.exists():
            return self.fallback_chat_id

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.fallback_chat_id

        if not isinstance(data, dict):
            return self.fallback_chat_id

        return str(data.get("target_chat_id") or self.fallback_chat_id).strip()

    def set(self, chat_id: int | str) -> str:
        value = str(chat_id).strip()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps({"target_chat_id": value}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)
        return value
