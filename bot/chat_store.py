from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Chat, TelegramObject


ChatRecord = dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._chats = self._load()

    def _load(self) -> dict[str, ChatRecord]:
        if not self.path.exists():
            return {}

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(raw, dict):
            return {}

        return {str(chat_id): chat for chat_id, chat in raw.items() if isinstance(chat, dict)}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._chats, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def upsert(self, chat: Chat | None) -> None:
        if chat is None:
            return

        chat_id = str(chat.id)
        existing = self._chats.get(chat_id, {})
        now = utc_now()

        self._chats[chat_id] = {
            "id": chat.id,
            "type": chat.type,
            "title": chat.title or "",
            "username": chat.username or "",
            "first_name": chat.first_name or "",
            "last_name": chat.last_name or "",
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "message_count": int(existing.get("message_count") or 0) + 1,
        }
        self._save()

    def all(self) -> list[ChatRecord]:
        return sorted(
            self._chats.values(),
            key=lambda chat: str(chat.get("last_seen", "")),
            reverse=True,
        )


class ChatTrackingMiddleware(BaseMiddleware):
    def __init__(self, chat_store: ChatStore) -> None:
        self.chat_store = chat_store

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat = getattr(event, "chat", None)
        if isinstance(chat, Chat):
            self.chat_store.upsert(chat)
            return await handler(event, data)

        message = getattr(event, "message", None)
        message_chat = getattr(message, "chat", None)
        if isinstance(message_chat, Chat):
            self.chat_store.upsert(message_chat)

        return await handler(event, data)
