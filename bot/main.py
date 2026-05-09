from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommandScopeChat, Message

from bot.chat_store import ChatStore, ChatTrackingMiddleware
from bot.config import Config, ROOT_DIR, load_config
from bot.console_server import start_console_server


router = Router(name="control")


STRANGER_REPLIES = [
    "Huh? why are you here, get outta here, i only speak with reality",
    "i said get outta here",
    "i dont speak",
]
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


def parse_target_chat_id(config: Config) -> int | str | None:
    target = config.default_chat_id.strip()
    if not target:
        return None

    try:
        return int(target)
    except ValueError:
        return target


async def send_stranger_reply(message: Message) -> None:
    sender_id = user_id(message)
    if sender_id is None:
        return

    count = stranger_counts.get(sender_id, 0)
    if count >= len(STRANGER_REPLIES):
        return

    stranger_counts[sender_id] = count + 1
    await message.answer(STRANGER_REPLIES[count])


async def copy_to_target(message: Message, bot: Bot, config: Config) -> None:
    target_chat_id = parse_target_chat_id(config)
    if target_chat_id is None:
        await message.answer("TARGET_CHAT_ID is not set on the server.")
        return

    try:
        sent = await bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await message.answer(f"sent #{sent.message_id}")
    except TelegramAPIError as exc:
        await message.answer(f"could not send: {exc}")


@router.message(CommandStart())
async def start(message: Message, config: Config) -> None:
    if is_admin(message, config):
        await message.answer("admin mode. send anything here and i will post it to the target chat.")
        return

    await send_stranger_reply(message)


@router.message(Command("chatid"))
@router.channel_post(Command("chatid"))
async def chatid(message: Message, config: Config) -> None:
    if message.chat.type != ChatType.CHANNEL and not is_admin(message, config):
        if message.chat.type == ChatType.PRIVATE:
            await send_stranger_reply(message)
        return

    username = f"\nUsername: @{message.chat.username}" if message.chat.username else ""
    await message.answer(
        f"Chat: {chat_label(message)}\n"
        f"Type: {message.chat.type}\n"
        f"ID: {message.chat.id}"
        f"{username}"
    )


@router.message()
async def handle_message(message: Message, bot: Bot, config: Config) -> None:
    if message.chat.type != ChatType.PRIVATE:
        return

    if is_admin(message, config):
        await copy_to_target(message, bot, config)
        return

    await send_stranger_reply(message)


async def run(config: Config) -> None:
    config.validate()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    chat_store = ChatStore(ROOT_DIR / "data" / "bot-chats.json")
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
