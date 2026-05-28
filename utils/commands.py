
from telegram import Bot

from aiogram.types import BotCommand
from data.search_items import SEARCH_ITEMS
async def set_commands(bot: Bot):
    commands = []

    for key, value in SEARCH_ITEMS.items():
        commands.append(
            BotCommand(
                command=key,
                description=value
            )
        )

    await bot.set_my_commands(commands)