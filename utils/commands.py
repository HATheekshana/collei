
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand
from data.search_items import SEARCH_ITEMS

MAX_BOT_COMMANDS = 100
DEFAULT_COMMANDS = [
    BotCommand(command="start", description="Show welcome message"),
    BotCommand(command="allcommands", description="List every available search command"),
    BotCommand(command="addarti", description="Add a new artifact"),
]

async def set_commands(bot: Bot):
    commands = DEFAULT_COMMANDS.copy()

    remaining = MAX_BOT_COMMANDS - len(commands)
    if remaining > 0:
        for key, value in list(SEARCH_ITEMS.items())[:remaining]:
            commands.append(
                BotCommand(
                    command=key,
                    description=value
                )
            )

    try:
        await bot.set_my_commands(commands)
    except TelegramBadRequest as exc:
        logging.warning("Could not register bot commands: %s", exc)
    except Exception as exc:
        logging.exception("Unexpected error registering bot commands: %s", exc)