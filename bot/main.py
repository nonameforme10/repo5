from __future__ import annotations

import asyncio
import logging
import sys
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommandScopeChat, Message

from bot.chat_store import ChatStore, ChatTrackingMiddleware
from bot.config import Config, ROOT_DIR, load_config
from bot.console_server import start_console_server
from bot.reply_store import ReplyStore
from bot.target_store import TargetStore


router = Router(name="control")


stranger_counts: dict[int, int] = {}


def user_id(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


def is_admin(message: Message, config: Config) -> bool:
    return config.is_admin(user_id(message))


def chat_label(message: Message) -> str:
    return message.chat.title or message.chat.full_name or message.chat.username or str(message.chat.id)


async def set_commands(bot: Bot, config: Config) -> None:
    await bot.delete_my_commands()
    for admin_id in config.admin_ids:
        try:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as exc:
            logging.warning("Could not clear private admin commands for %s: %s", admin_id, exc)


def normalize_chat_id(value: str) -> int | str | None:
    target = value.strip()
    if not target:
        return None

    if "t.me/+" in target or "t.me/joinchat/" in target:
        return None

    if target.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        parsed = urlparse(target if target.startswith(("http://", "https://")) else f"https://{target}")
        username = parsed.path.strip("/").split("/", 1)[0]
        if username:
            return f"@{username.lstrip('@')}"
        return None

    try:
        return int(target)
    except ValueError:
        return target if target.startswith("@") else None


async def send_stranger_reply(message: Message, reply_store: ReplyStore) -> None:
    sender_id = user_id(message)
    if sender_id is None:
        return

    count = stranger_counts.get(sender_id, 0)
    reply = reply_store.reply_for_count(count)
    if reply is None:
        return

    stranger_counts[sender_id] = count + 1
    await message.answer(reply)


def forwarded_chat_id(message: Message) -> int | str | None:
    origin = getattr(message, "forward_origin", None)
    origin_chat = getattr(origin, "chat", None)
    if origin_chat is not None:
        return getattr(origin_chat, "id", None)

    old_forward_chat = getattr(message, "forward_from_chat", None)
    if old_forward_chat is not None:
        return getattr(old_forward_chat, "id", None)

    return None


async def maybe_set_target(message: Message, target_store: TargetStore) -> bool:
    chat_id = forwarded_chat_id(message)
    if chat_id is not None:
        saved = target_store.set(chat_id)
        await message.answer(f"target saved: {saved}")
        return True

    text = (message.text or "").strip()
    if not text:
        return False

    if "t.me/+" in text or "t.me/joinchat/" in text:
        await message.answer("private invite links cannot be used. send the -100... chat id or forward a post from the target channel.")
        return True

    normalized = normalize_chat_id(text)
    if normalized is None:
        return False

    if isinstance(normalized, int) or str(normalized).startswith("@"):
        saved = target_store.set(normalized)
        await message.answer(f"target saved: {saved}")
        return True

    return False


async def copy_to_target(message: Message, bot: Bot, target_store: TargetStore) -> None:
    target_chat_id = normalize_chat_id(target_store.get())
    if target_chat_id is None:
        await message.answer("target chat is not set. send me the -100... chat id once, or forward a post from the target channel.")
        return

    try:
        sent = await bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await message.answer(f"sent #{sent.message_id}")
    except TelegramAPIError as exc:
        await message.answer(
            f"could not send: {exc}\n\n"
            "Fix: add the bot to the target chat/channel, make it admin if it is a channel, "
            "then send me the real -100... chat id again."
        )


@router.message(CommandStart())
async def start(message: Message, config: Config, reply_store: ReplyStore) -> None:
    if is_admin(message, config):
        await message.answer("admin mode. send anything here and i will post it to the target chat.")
        return

    await send_stranger_reply(message, reply_store)


@router.message(Command("chatid"))
@router.channel_post(Command("chatid"))
async def chatid(message: Message, config: Config, reply_store: ReplyStore) -> None:
    if message.chat.type != ChatType.CHANNEL and not is_admin(message, config):
        if message.chat.type == ChatType.PRIVATE:
            await send_stranger_reply(message, reply_store)
        return

    username = f"\nUsername: @{message.chat.username}" if message.chat.username else ""
    await message.answer(
        f"Chat: {chat_label(message)}\n"
        f"Type: {message.chat.type}\n"
        f"ID: {message.chat.id}"
        f"{username}"
    )


@router.message()
async def handle_message(
    message: Message,
    bot: Bot,
    config: Config,
    target_store: TargetStore,
    reply_store: ReplyStore,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        return

    if is_admin(message, config):
        if await maybe_set_target(message, target_store):
            return

        await copy_to_target(message, bot, target_store)
        return

    await send_stranger_reply(message, reply_store)


async def run(config: Config) -> None:
    config.validate()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    chat_store = ChatStore(ROOT_DIR / "data" / "bot-chats.json")
    target_store = TargetStore(ROOT_DIR / "data" / "target-chat.json", fallback_chat_id=config.default_chat_id)
    reply_store = ReplyStore(ROOT_DIR / "bot" / "ragebaits.json")
    console_runner = None

    dispatcher.message.middleware(ChatTrackingMiddleware(chat_store))
    dispatcher.channel_post.middleware(ChatTrackingMiddleware(chat_store))
    dispatcher.callback_query.middleware(ChatTrackingMiddleware(chat_store))
    dispatcher.include_router(router)

    try:
        console_runner = await start_console_server(bot, config, chat_store)
        if console_runner:
            logging.info("Console running at %s", config.console_url)

        await set_commands(bot, config)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            config=config,
            target_store=target_store,
            reply_store=reply_store,
        )
    finally:
        if console_runner:
            await console_runner.cleanup()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    asyncio.run(run(load_config()))


if __name__ == "__main__":
    main()
