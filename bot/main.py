from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BotCommandScopeChat, Message

from bot.chat_store import ChatStore, ChatTrackingMiddleware
from bot.config import Config, ROOT_DIR, load_config
from bot.console_server import start_console_server


router = Router(name="control")


PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Show bot help"),
    BotCommand(command="chatid", description="Show this chat ID"),
]


ADMIN_COMMANDS = [
    BotCommand(command="console", description="Show the browser console address"),
    BotCommand(command="say", description="Make the bot say text in this chat"),
]


def user_id(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


def is_admin(message: Message, config: Config) -> bool:
    return config.is_admin(user_id(message))


def chat_label(message: Message) -> str:
    return message.chat.title or message.chat.full_name or message.chat.username or str(message.chat.id)


async def set_commands(bot: Bot, config: Config) -> None:
    await bot.delete_my_commands()
    await bot.set_my_commands(PUBLIC_COMMANDS)

    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands([*PUBLIC_COMMANDS, *ADMIN_COMMANDS], scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as exc:
            logging.warning("Could not set private admin commands for %s: %s", admin_id, exc)


@router.message(CommandStart())
async def start(message: Message, config: Config) -> None:
    admin_line = ""
    if is_admin(message, config):
        admin_line = (
            "\n\nAdmin commands:"
            "\n/console - show browser console URL"
            "\n/say your text - send a message as the bot"
        )

    await message.answer(
        "Bot is online.\n\n"
        "Use /chatid inside a group, channel discussion, or DM to get the target chat ID. "
        "Open the browser console to send text, links, emoji, GIFs, files, videos, and more."
        f"{admin_line}"
    )


@router.message(Command("chatid"))
@router.channel_post(Command("chatid"))
async def chatid(message: Message) -> None:
    username = f"\nUsername: @{message.chat.username}" if message.chat.username else ""
    await message.answer(
        f"Chat: {chat_label(message)}\n"
        f"Type: {message.chat.type}\n"
        f"ID: {message.chat.id}"
        f"{username}"
    )


@router.message(Command("console"))
async def console(message: Message, config: Config) -> None:
    if not is_admin(message, config):
        await message.answer("Only configured admins can use this command.")
        return

    key_note = "\nConsole key is required." if config.console_api_key else ""
    await message.answer(f"Browser console: {config.console_url}{key_note}")


@router.message(Command("say"))
async def say(message: Message, bot: Bot, config: Config) -> None:
    if not is_admin(message, config):
        await message.answer("Only configured admins can use /say.")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /say your message")
        return

    await bot.send_message(chat_id=message.chat.id, text=parts[1].strip(), parse_mode=None)


@router.message(F.text)
async def mention_reply(message: Message, bot: Bot) -> None:
    if not message.text:
        return

    me = await bot.get_me()
    username = f"@{me.username}".lower() if me.username else ""
    is_mentioned = bool(username and username in message.text.lower())
    is_reply_to_bot = bool(message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == me.id)

    if is_mentioned or is_reply_to_bot:
        await message.reply("I am here. My owner can speak through me from the console.")


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
