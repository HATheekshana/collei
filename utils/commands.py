import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllPrivateChats,
)

from data.search_items import COMMAND

MAX_BOT_COMMANDS = 100

DEFAULT_COMMANDS = [
    BotCommand(command="start", description="Show welcome message"),
    BotCommand(command="allcommands", description="List every available search command"),
    BotCommand(command="addarti", description="Add a new artifact"),
]


async def set_commands(bot: Bot):
    try:
        commands = DEFAULT_COMMANDS.copy()

        # Add dynamic commands safely
        remaining = MAX_BOT_COMMANDS - len(commands)

        if remaining > 0:
            for key, value in list(COMMAND.items())[:remaining]:
                # Telegram command rules: lowercase, no spaces
                safe_key = key.lower().replace(" ", "_")

                commands.append(
                    BotCommand(
                        command=safe_key,
                        description=value[:100],  # Telegram max description length safety
                    )
                )

        # 1️⃣ Default scope (global)
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeDefault()
        )

        # 2️⃣ Private chats scope (fixes "OFF" issue in many cases)
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeAllPrivateChats()
        )

        logging.info("Bot commands successfully registered (%d commands)", len(commands))

    except TelegramBadRequest as exc:
        logging.warning("Telegram rejected command registration: %s", exc)

    except Exception as exc:
        logging.exception("Unexpected error registering bot commands: %s", exc)