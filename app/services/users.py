from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ReminderSettings, User


async def get_or_create_user(session: AsyncSession, telegram_id: int, name: str | None = None) -> User:
    settings = get_settings()
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        if name and user.name != name:
            user.name = name
            await session.commit()
            await session.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        name=name,
        timezone=settings.default_timezone,
        calorie_target=settings.default_calorie_target,
        protein_target=settings.default_protein_target,
        fat_target=settings.default_fat_target,
        carb_target=settings.default_carb_target,
    )
    session.add(user)
    await session.flush()
    session.add(
        ReminderSettings(
            user_id=user.id,
            breakfast_time=time(7, 0),
            lunch_time=time(11, 0),
            dinner_time=time(17, 0),
            evening_report_time=time(17, 0),
            enabled=True,
        )
    )
    await session.commit()
    await session.refresh(user)
    return user
