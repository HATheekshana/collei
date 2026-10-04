from aiogram import Bot
from aiogram.types import BotCommand


async def set_commands(bot: Bot) -> None:
    """Register the public commands shown in Telegram's bot menu."""
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open the bot menu"),
            BotCommand(command="help", description="Show help"),
            BotCommand(command="removegroup", description="Remove the bot from this group"),
        ]
    )
