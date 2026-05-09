from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]


for env_file in (
    ROOT_DIR / ".env.local",
    ROOT_DIR / ".env",
    ROOT_DIR / "functions" / ".env",
    ROOT_DIR / "bot" / ".env",
):
    if env_file.exists():
        load_dotenv(env_file, override=False)


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value

    return default


def _csv_ints(value: str) -> set[int]:
    ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            pass
    return ids


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    default_chat_id: str
    console_host: str
    console_port: int
    console_api_key: str
    console_public_url: str
    console_allowed_origins: set[str]
    console_enabled: bool
    max_upload_mb: int
    allow_unsafe_console: bool

    def is_admin(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.admin_ids

    @property
    def console_url(self) -> str:
        if self.console_public_url:
            if "?" in self.console_public_url or "#" in self.console_public_url:
                return self.console_public_url
            return self.console_public_url.rstrip("/") + "/"

        host = "127.0.0.1" if self.console_host in {"0.0.0.0", "::"} else self.console_host
        return f"http://{host}:{self.console_port}/"

    @property
    def console_is_publicly_bound(self) -> bool:
        return self.console_host in {"0.0.0.0", "::", ""}

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError("Telegram bot token is missing. Set TELEGRAM_BOT_TOKEN in .env.")

        publicly_reachable = self.console_is_publicly_bound or bool(self.console_public_url)
        if self.console_enabled and publicly_reachable and not self.console_api_key and not self.allow_unsafe_console:
            raise RuntimeError(
                "Refusing to expose the console without CONSOLE_API_KEY. "
                "Set CONSOLE_API_KEY or remove CONSOLE_PUBLIC_URL for local-only use."
            )


def load_config() -> Config:
    admin_ids = set[int]()
    admin_ids.update(_csv_ints(os.getenv("ADMIN_IDS", "")))
    admin_ids.update(_csv_ints(os.getenv("BOT_ADMIN_IDS", "")))
    admin_ids.update(_csv_ints(os.getenv("ADMINID", "")))

    return Config(
        bot_token=_first_env(
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM-BOT-TOKEN",
            "BOT_TOKEN",
            "BOT-TOKEN",
        ),
        admin_ids=admin_ids,
        default_chat_id=_first_env("TARGET_CHAT_ID", "DEFAULT_CHAT_ID", "CHANNEL_ID"),
        console_host=_first_env("CONSOLE_HOST", default="127.0.0.1"),
        console_port=_int_env("CONSOLE_PORT", 8080),
        console_api_key=_first_env("CONSOLE_API_KEY", "CONSOLE_PASSWORD"),
        console_public_url=_first_env("CONSOLE_PUBLIC_URL", "PUBLIC_CONSOLE_URL"),
        console_allowed_origins={
            origin.rstrip("/")
            for origin in _first_env("CONSOLE_ALLOWED_ORIGINS", "CORS_ALLOWED_ORIGINS").split(",")
            if origin.strip()
        },
        console_enabled=_bool_env("CONSOLE_ENABLED", True),
        max_upload_mb=_int_env("MAX_UPLOAD_MB", 60),
        allow_unsafe_console=_bool_env("ALLOW_UNSAFE_CONSOLE", False),
    )
