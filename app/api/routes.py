import secrets
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.models import ActivityLog, Food, MealLog, User
from app.schemas import ActivityLogRead, ActivitySyncIn, FoodRead, MealLogRead
from app.services.activity import get_activity_for_date, upsert_activity_log
from app.services.reports import build_daily_report, build_monthly_report, build_weekly_report, build_year_report

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/foods", response_model=list[FoodRead])
async def list_foods(session: AsyncSession = Depends(get_session)) -> list[Food]:
    result = await session.execute(select(Food).order_by(Food.name))
    return list(result.scalars().all())


async def _require_admin_api(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_admin_token:
        raise HTTPException(status_code=403, detail="API admin token is not configured")
    if not secrets.compare_digest(x_admin_token or "", settings.api_admin_token):
        raise HTTPException(status_code=403, detail="Invalid admin token")


async def _require_health_sync(x_health_sync_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.health_sync_token:
        raise HTTPException(status_code=403, detail="Health sync token is not configured")
    if not secrets.compare_digest(x_health_sync_token or "", settings.health_sync_token):
        raise HTTPException(status_code=403, detail="Invalid health sync token")


@router.get("/users/{telegram_id}/today")
async def today(
    telegram_id: int,
    _: None = Depends(_require_admin_api),
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user(session, telegram_id)
    return await build_daily_report(session, user)


@router.get("/users/{telegram_id}/week")
async def week(
    telegram_id: int,
    _: None = Depends(_require_admin_api),
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user(session, telegram_id)
    return await build_weekly_report(session, user)


@router.get("/users/{telegram_id}/month")
async def month(
    telegram_id: int,
    _: None = Depends(_require_admin_api),
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user(session, telegram_id)
    return await build_monthly_report(session, user)


@router.get("/users/{telegram_id}/year")
async def year(
    telegram_id: int,
    _: None = Depends(_require_admin_api),
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user(session, telegram_id)
    return await build_year_report(session, user)


@router.get("/users/{telegram_id}/logs", response_model=list[MealLogRead])
async def logs(
    telegram_id: int,
    _: None = Depends(_require_admin_api),
    session: AsyncSession = Depends(get_session),
) -> list[MealLog]:
    user = await _get_user(session, telegram_id)
    result = await session.execute(
        select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.datetime.desc()).limit(100)
    )
    return list(result.scalars().all())


@router.post("/integrations/health/activity", response_model=ActivityLogRead)
async def sync_activity(
    payload: ActivitySyncIn,
    _: None = Depends(_require_health_sync),
    session: AsyncSession = Depends(get_session),
) -> ActivityLog:
    user = await _get_user(session, payload.telegram_id)
    return await upsert_activity_log(session, user, payload)


@router.get("/users/{telegram_id}/activity/{activity_date}", response_model=list[ActivityLogRead])
async def activity_for_day(
    telegram_id: int,
    activity_date: date,
    _: None = Depends(_require_admin_api),
    session: AsyncSession = Depends(get_session),
) -> list[ActivityLog]:
    user = await _get_user(session, telegram_id)
    return await get_activity_for_date(session, user, activity_date)


async def _get_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
