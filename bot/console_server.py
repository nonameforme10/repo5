from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, LinkPreviewOptions

from bot.chat_store import ChatStore
from bot.config import Config, ROOT_DIR


MEDIA_METHODS = {
    "photo": "send_photo",
    "video": "send_video",
    "animation": "send_animation",
    "document": "send_document",
    "audio": "send_audio",
    "voice": "send_voice",
    "sticker": "send_sticker",
}


def allowed_origin(config: Config, origin: str | None) -> str | None:
    if not origin:
        return None

    clean_origin = origin.rstrip("/")
    if "*" in config.console_allowed_origins:
        return origin

    if clean_origin in config.console_allowed_origins:
        return origin

    return None


@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.StreamResponse:
    config: Config = request.app["config"]
    origin = allowed_origin(config, request.headers.get("Origin"))

    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)

    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Console-Key"
        response.headers["Access-Control-Max-Age"] = "86400"
        response.headers["Vary"] = "Origin"

    return response


def json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


def check_console_key(request: web.Request) -> web.Response | None:
    config: Config = request.app["config"]
    if not config.console_api_key:
        return None

    provided = request.headers.get("X-Console-Key", "") or request.query.get("key", "")
    if provided == config.console_api_key:
        return None

    return json_error("Console key is missing or invalid.", status=401)


def parse_chat_id(value: Any) -> int | str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Chat ID is required.")

    if "t.me/+" in text or "t.me/joinchat/" in text:
        raise ValueError(
            "Telegram private invite links cannot be used as chat IDs. "
            "Add the bot as a channel admin, then use /chatid to get the -100... ID."
        )

    if text.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        parsed = urlparse(text if text.startswith(("http://", "https://")) else f"https://{text}")
        username = parsed.path.strip("/").split("/", 1)[0]
        if username:
            return f"@{username.lstrip('@')}"

    try:
        return int(text)
    except ValueError:
        return text


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def combine_text_and_link(text: str, link: str) -> str:
    text = text.strip()
    link = link.strip()
    if text and link:
        return f"{text}\n{link}"
    return text or link


async def request_data(request: web.Request) -> tuple[dict[str, Any], Any]:
    if request.content_type.lower().startswith("multipart/"):
        form = await request.post()
        return dict(form), form.get("file")

    if request.content_type.lower() == "application/json":
        return await request.json(), None

    form = await request.post()
    return dict(form), form.get("file")


def input_media(data: dict[str, Any], file_field: Any) -> str | BufferedInputFile:
    url = str(data.get("url") or "").strip()
    if url:
        return url

    if file_field is None or not hasattr(file_field, "file"):
        raise ValueError("Upload a file or paste a direct media URL.")

    filename = getattr(file_field, "filename", "") or "upload"
    return BufferedInputFile(file_field.file.read(), filename=filename)


async def index(_: web.Request) -> web.StreamResponse:
    path = ROOT_DIR / "index.html"
    if not path.exists():
        return web.Response(text="index.html was not found.", status=404)

    return web.FileResponse(path)


async def status(request: web.Request) -> web.Response:
    auth_error = check_console_key(request)
    if auth_error:
        return auth_error

    bot: Bot = request.app["bot"]
    me = await bot.get_me()
    config: Config = request.app["config"]

    return web.json_response(
        {
            "ok": True,
            "bot": {
                "id": me.id,
                "username": me.username,
                "name": me.full_name,
            },
            "console": {
                "host": config.console_host,
                "port": config.console_port,
                "url": config.console_url,
                "default_chat_id": config.default_chat_id,
                "auth_required": bool(config.console_api_key),
                "max_upload_mb": config.max_upload_mb,
                "allowed_origins": sorted(config.console_allowed_origins),
            },
        }
    )


async def chats(request: web.Request) -> web.Response:
    auth_error = check_console_key(request)
    if auth_error:
        return auth_error

    chat_store: ChatStore = request.app["chat_store"]
    return web.json_response({"ok": True, "chats": chat_store.all()})


async def send(request: web.Request) -> web.Response:
    auth_error = check_console_key(request)
    if auth_error:
        return auth_error

    bot: Bot = request.app["bot"]

    try:
        data, file_field = await request_data(request)
        config: Config = request.app["config"]
        chat_id = parse_chat_id(data.get("chat_id") or config.default_chat_id)
        send_type = str(data.get("type") or "message").strip().lower()
        text = combine_text_and_link(str(data.get("text") or ""), str(data.get("link") or ""))
        caption = str(data.get("caption") or "").strip() or None
        disable_preview = truthy(data.get("disable_preview"))

        if send_type == "message":
            if not text:
                return json_error("Message text or link is required.")

            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=None,
                link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
            )
            return web.json_response({"ok": True, "message_id": message.message_id})

        if send_type not in MEDIA_METHODS:
            return json_error(f"Unsupported send type: {send_type}")

        media = input_media(data, file_field)
        method = getattr(bot, MEDIA_METHODS[send_type])
        kwargs: dict[str, Any] = {"chat_id": chat_id, send_type: media}

        if send_type != "sticker" and caption:
            kwargs["caption"] = caption
            kwargs["parse_mode"] = None

        message = await method(**kwargs)
        return web.json_response({"ok": True, "message_id": message.message_id})
    except ValueError as exc:
        return json_error(str(exc))
    except TelegramAPIError as exc:
        return json_error(str(exc), status=502)


def create_console_app(bot: Bot, config: Config, chat_store: ChatStore) -> web.Application:
    app = web.Application(
        client_max_size=max(1, config.max_upload_mb) * 1024**2,
        middlewares=[cors_middleware],
    )
    app["bot"] = bot
    app["config"] = config
    app["chat_store"] = chat_store
    app.router.add_get("/", index)
    app.router.add_get("/console", index)
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/chats", chats)
    app.router.add_post("/api/send", send)
    app.router.add_options("/api/{tail:.*}", lambda _: web.Response(status=204))
    return app


async def start_console_server(bot: Bot, config: Config, chat_store: ChatStore) -> web.AppRunner | None:
    if not config.console_enabled:
        return None

    app = create_console_app(bot, config, chat_store)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.console_host, config.console_port)
    await site.start()
    return runner
