from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BridgeRecord = dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BridgeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._records = self._load()

    def _load(self) -> dict[str, BridgeRecord]:
        if not self.path.exists():
            return {}

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(raw, dict):
            return {}

        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    @staticmethod
    def _key(admin_chat_id: int | str, admin_message_id: int | str) -> str:
        return f"{admin_chat_id}:{admin_message_id}"

    def set(
        self,
        admin_chat_id: int,
        admin_message_id: int,
        target_chat_id: int | str,
        target_message_id: int,
    ) -> None:
        self._records[self._key(admin_chat_id, admin_message_id)] = {
            "admin_chat_id": admin_chat_id,
            "admin_message_id": admin_message_id,
            "target_chat_id": target_chat_id,
            "target_message_id": target_message_id,
            "created_at": utc_now(),
        }
        self._save()

    def get(self, admin_chat_id: int, admin_message_id: int) -> BridgeRecord | None:
        return self._records.get(self._key(admin_chat_id, admin_message_id))
