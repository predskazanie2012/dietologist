import asyncio
import logging

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.access import WhitelistMiddleware
from app.bot.handlers import router
from app.bot.menu import bot_commands
from app.config import get_settings
from app.services.reminders import load_all_reminders


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    await bot.delete_my_commands()
    await bot.set_my_commands(bot_commands())
    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware())
    dp.include_router(router)

    scheduler = AsyncIOScheduler()
    scheduler.start()
    dp.workflow_data["scheduler"] = scheduler
    await load_all_reminders(scheduler, bot)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
