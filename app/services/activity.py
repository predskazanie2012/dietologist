from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityLog, User
from app.schemas import ActivitySyncIn


async def upsert_activity_log(session: AsyncSession, user: User, payload: ActivitySyncIn) -> ActivityLog:
    result = await session.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.date == payload.date,
            ActivityLog.source == payload.source,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        log = ActivityLog(user_id=user.id, date=payload.date, source=payload.source)
        session.add(log)

    log.steps = payload.steps
    log.active_calories = payload.active_calories
    log.total_calories = payload.total_calories
    log.distance_m = payload.distance_m
    log.sleep_minutes = payload.sleep_minutes
    log.avg_heart_rate = payload.avg_heart_rate
    log.raw_json = payload.raw
    await session.commit()
    await session.refresh(log)
    return log


async def get_activity_for_date(session: AsyncSession, user: User, day: date) -> list[ActivityLog]:
    result = await session.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id, ActivityLog.date == day).order_by(ActivityLog.source)
    )
    return list(result.scalars().all())
