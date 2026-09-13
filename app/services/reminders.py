import logging
from datetime import time
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session_maker
from app.models import ReminderSettings, User
from app.services.access import is_allowed_telegram_user
from app.services.reports import build_daily_report, format_daily_summary

logger = logging.getLogger(__name__)


async def send_meal_reminder(bot: Bot, user_id: int, label: str) -> None:
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user or not is_allowed_telegram_user(user.telegram_id):
            return

        report = await build_daily_report(session, user)
        await bot.send_message(
            user.telegram_id,
            _format_reminder(label, report),
        )


async def send_evening_report(bot: Bot, user_id: int) -> None:
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user or not is_allowed_telegram_user(user.telegram_id):
            return

        from app.services.reports import format_daily_report

        report = await build_daily_report(session, user)
        await bot.send_message(user.telegram_id, format_daily_report(report))


def _format_reminder(label: str, report) -> str:
    return (
        f"{label}\n"
        "Если уже ела, ничего делать не нужно.\n\n"
        f"{format_daily_summary(report)}"
    )

def _trigger(run_time: time, timezone: str) -> CronTrigger:
    return CronTrigger(hour=run_time.hour, minute=run_time.minute, timezone=ZoneInfo(timezone))


def schedule_user_reminders(scheduler: AsyncIOScheduler, bot: Bot, user: User, settings: ReminderSettings) -> None:
    for suffix in ("breakfast", "lunch", "dinner", "evening"):
        job_id = f"user:{user.id}:{suffix}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    if not settings.enabled or not is_allowed_telegram_user(user.telegram_id):
        return

    scheduler.add_job(
        send_meal_reminder,
        _trigger(settings.breakfast_time, user.timezone),
        args=[bot, user.id, "Доброе утро. Мягкое напоминание про завтрак."],
        id=f"user:{user.id}:breakfast",
        replace_existing=True,
    )
    scheduler.add_job(
        send_meal_reminder,
        _trigger(settings.lunch_time, user.timezone),
        args=[bot, user.id, "Напоминание про обед."],
        id=f"user:{user.id}:lunch",
        replace_existing=True,
    )
    scheduler.add_job(
        send_meal_reminder,
        _trigger(settings.dinner_time, user.timezone),
        args=[bot, user.id, "Напоминание про вечерний приём пищи."],
        id=f"user:{user.id}:dinner",
        replace_existing=True,
    )

async def load_all_reminders(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(User, ReminderSettings).join(ReminderSettings))
        for user, settings in result.all():
            schedule_user_reminders(scheduler, bot, user, settings)
    logger.info("Reminder jobs loaded: %s", len(scheduler.get_jobs()))
