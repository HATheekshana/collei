import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)

from data.search_items import SEARCH_ITEMS

MAX_BOT_COMMANDS = 200

DEFAULT_COMMANDS = [
    BotCommand(command="start", description="Show welcome message"),
    BotCommand(command="search", description="Search characters and artifacts"),
    BotCommand(command="next", description="Show next banner countdowns"),
    BotCommand(command="current", description="Show current banner countdowns"),
    BotCommand(command="allcommands", description="List all commands"),
    BotCommand(command="addarti", description="Add artifact info"),
    BotCommand(command="bossimg", description="[Admin] Set boss image (reply to photo)"),
]


async def set_commands(bot: Bot):
    try:
        commands = DEFAULT_COMMANDS.copy()

        remaining = MAX_BOT_COMMANDS - len(commands)

        if remaining > 0:
            for key, value in list(SEARCH_ITEMS.items())[:remaining]:
                safe_key = key.lower().replace(" ", "_")

                commands.append(
                    BotCommand(
                        command=safe_key,
                        description=value[:200],
                    )
                )

        # 1️⃣ Private chats
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeAllPrivateChats()
        )

        # 2️⃣ Groups
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeAllGroupChats()
        )

        # 3️⃣ Group admins / full control
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeAllChatAdministrators()
        )

        # 4️⃣ Default fallback (VERY IMPORTANT for BotFather UI)
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeDefault()
        )

        logging.info("Commands registered for ALL scopes (%d commands)", len(commands))

    except TelegramBadRequest as exc:
        logging.warning("Telegram rejected command registration: %s", exc)

    except Exception as exc:
        logging.exception("Unexpected error: %s", exc)