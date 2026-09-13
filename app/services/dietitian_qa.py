from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.config import get_settings
from app.models import MealLog, User
from app.services.reports import build_daily_report


SYSTEM_PROMPT = """
Ты личный помощник по пищевому дневнику для одной пользовательницы.
Отвечай коротко, спокойно и по делу на русском языке.
Всегда говори о себе только в мужском роде, даже если местоимение «я» опущено: «получил», «записал», «понял», «готов». Никогда не используй о себе женские формы.
Это оценочный пищевой дневник, не медицинская диагностика.
Не ставь диагнозы. Не предлагай БАДы, витамины, добавки или лекарства.
Рекомендации давай только через обычные продукты и блюда.
Если советуешь еду, пиши граммы и понятную меру в скобках: 120 г (1 ладонь), 200 г (1 большая миска), 10 г (1 ч. л.).
Не добавляй вводные слова оценки в рекомендациях.
Если данных в дневнике не хватает, прямо скажи, что видно только по записанным данным.
Один ответ — 3-7 коротких строк, без давления и запугивания.
""".strip()


async def answer_dietitian_question(session: AsyncSession, user: User, question: str) -> str:
    report = await build_daily_report(session, user)
    result = await session.execute(
        select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.datetime.desc()).limit(12)
    )
    logs = list(result.scalars().all())
    context = _build_context(user, report, logs)

    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback_answer(question, context)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=settings.openai_model,
        instructions=SYSTEM_PROMPT,
        input=(
            f"Контекст дневника:\n{context}\n\n"
            f"Вопрос пользовательницы:\n{question}\n\n"
            "Ответь как личный диетолог-дневник: по фактам из записей, мягко, без медицинских заявлений."
        ),
    )
    return (response.output_text or "Не смог сформировать ответ. Попробуй спросить короче.").strip()


def _build_context(user: User, report, logs: list[MealLog]) -> str:
    lines = [
        f"Цели на день: {user.calorie_target:.0f} ккал, белок {user.protein_target:.0f} г, "
        f"жиры {user.fat_target:.0f} г, углеводы {user.carb_target:.0f} г.",
        f"Сегодня записано: {report.calories_fact:.0f} ккал, белок {report.protein_fact:.0f} г, "
        f"жиры {report.fat_fact:.0f} г, углеводы {report.carbs_fact:.0f} г, клетчатка {report.fiber_fact:.0f} г.",
    ]
    if any([report.steps, report.active_calories, report.total_burned_calories, report.sleep_minutes, report.avg_heart_rate]):
        lines.append(
            f"Активность сегодня: шаги {report.steps}, активные калории {report.active_calories:.0f}, "
            f"всего потрачено {report.total_burned_calories:.0f}, сон {report.sleep_minutes / 60:.1f} ч, "
            f"средний пульс {report.avg_heart_rate:.0f}." if report.avg_heart_rate else
            f"Активность сегодня: шаги {report.steps}, активные калории {report.active_calories:.0f}, "
            f"всего потрачено {report.total_burned_calories:.0f}, сон {report.sleep_minutes / 60:.1f} ч."
        )
    if logs:
        lines.append("Последние записи:")
        for log in logs:
            raw = (log.raw_user_input or log.notes or log.meal_type or "приём пищи").replace("\n", " ")[:180]
            lines.append(
                f"- {log.datetime:%d.%m %H:%M}: {raw}; {log.calories:.0f} ккал, "
                f"Б {log.protein:.0f}, Ж {log.fat:.0f}, У {log.carbs:.0f}"
            )
    else:
        lines.append("Сегодня в дневнике пока нет записей еды.")
    return "\n".join(lines)


def _fallback_answer(question: str, context: str) -> str:
    return (
        "Могу ответить только по записанному дневнику.\n"
        f"{context}\n"
        "Если еда была, но её нет в списке, запиши её текстом: например `утка 120 г, творог 150 г`."
    )
