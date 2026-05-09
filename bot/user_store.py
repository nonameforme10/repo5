from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User


UserRecord = dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UserStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._users = self._load()

    def _load(self) -> dict[str, UserRecord]:
        if not self.path.exists():
            return {}

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(raw, dict):
            return {}

        return {str(user_id): user for user_id, user in raw.items() if isinstance(user, dict)}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._users, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def upsert(self, user: User | None) -> None:
        if user is None or user.is_bot:
            return

        user_id = str(user.id)
        existing = self._users.get(user_id, {})
        now = utc_now()

        self._users[user_id] = {
            "id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "language_code": user.language_code or "",
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "message_count": int(existing.get("message_count") or 0) + 1,
        }
        self._save()

    def all(self) -> list[UserRecord]:
        return sorted(
            self._users.values(),
            key=lambda user: str(user.get("last_seen", "")),
            reverse=True,
        )


class UserTrackingMiddleware(BaseMiddleware):
    def __init__(self, user_store: UserStore) -> None:
        self.user_store = user_store

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if isinstance(user, User):
            self.user_store.upsert(user)

        return await handler(event, data)
