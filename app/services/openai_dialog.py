import json
import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import MealLog, User
from app.services.reports import build_daily_report

logger = logging.getLogger(__name__)


DialogActionName = Literal[
    "answer",
    "log_food",
    "update_last_meal",
    "log_weight",
    "show_today",
    "show_week",
    "advice",
    "clarify",
]


class DialogFoodItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    amount: str
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    fat: float = Field(ge=0)
    carbs: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class DialogMicronutrients(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vitamin_a: float = 0
    vitamin_c: float = 0
    vitamin_d: float = 0
    vitamin_e: float = 0
    vitamin_k: float = 0
    thiamin: float = 0
    riboflavin: float = 0
    niacin: float = 0
    pantothenic_acid: float = 0
    vitamin_b6: float = 0
    biotin: float = 0
    folate: float = 0
    vitamin_b12: float = 0
    choline: float = 0
    calcium: float = 0
    chloride: float = 0
    chromium: float = 0
    copper: float = 0
    fluoride: float = 0
    iodine: float = 0
    iron: float = 0
    magnesium: float = 0
    manganese: float = 0
    molybdenum: float = 0
    phosphorus: float = 0
    potassium: float = 0
    selenium: float = 0
    sodium: float = 0
    zinc: float = 0
    omega3: float = 0


class DialogFoodEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    items: list[DialogFoodItem] = Field(default_factory=list)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    fat: float = Field(ge=0)
    carbs: float = Field(ge=0)
    fiber: float = Field(default=0, ge=0)
    micronutrients: DialogMicronutrients = Field(default_factory=DialogMicronutrients)
    confidence: float = Field(ge=0, le=1)


class DialogDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: DialogActionName
    confidence: float = Field(ge=0, le=1)
    reply_text: str
    food: DialogFoodEstimate | None = None
    weight_kg: float | None = Field(default=None, ge=30, le=250)


SYSTEM_PROMPT = """
Ты полноценный ChatGPT-слой внутри Telegram-бота "личный диетолог".
Твоя задача: понять обычное сообщение пользовательницы и вернуть действие для пищевого дневника.

Правила:
- Отвечай и думай на русском языке.
- Всегда говори о себе только в мужском роде, даже если пользовательница — женщина и даже если местоимение «я» опущено: «получил», «записал», «понял», «готов». Никогда не используй о себе женские формы.
- Это оценочный пищевой дневник, не медицинская диагностика.
- Не ставь диагнозы и не предлагай лекарства, витамины, добавки или БАДы.
- Рекомендации давай только через обычные продукты и блюда.
- Если советуешь еду, пиши граммы и понятную меру в скобках: 120 г (1 ладонь), 200 г (1 большая миска), 10 г (1 ч. л.).
- Не добавляй вводные слова оценки в рекомендациях.
- Не пугай дефицитами. Пиши коротко, спокойно, конкретно.
- Если пользовательница сообщает, что она съела или выпила, выбери action=log_food.
- Если это уточнение/исправление последней записи: "там была утка", "не забудь сок", "это был борщ, а не масло", выбери action=update_last_meal.
- Если указан вес, выбери action=log_weight.
- Если вопрос про сегодня/остаток/калории, выбери show_today или answer.
- Если вопрос про неделю, выбери show_week или answer.
- Если просит совет, выбери advice или answer.
- Если это обычный вопрос, выбери answer.

Для log_food и update_last_meal:
- Заполни food итоговой оценкой КБЖУ.
- Если граммов нет, используй бытовые порции: стакан 200 мл, чашка/миска 250-300 г, яйцо 55 г, кусок хлеба 30-40 г, ложка масла 10-15 г.
- При update_last_meal оцени весь исправленный приём пищи целиком, насколько возможно из контекста последних записей.
- Явно отмечай оценочность, но не задавай лишний вопрос, если можно разумно посчитать.
- Микронутриенты оцени по возможности; если данных мало, ставь 0, но не придумывай экстремальные значения.
- Единицы micronutrients: vitamin_a мкг RAE; vitamin_c мг; vitamin_d мкг; vitamin_e мг; vitamin_k мкг; thiamin мг; riboflavin мг; niacin мг NE; pantothenic_acid мг; vitamin_b6 мг; biotin мкг; folate мкг DFE; vitamin_b12 мкг; choline мг; calcium мг; chloride мг; chromium мкг; copper мг; fluoride мг; iodine мкг; iron мг; magnesium мг; manganese мг; molybdenum мкг; phosphorus мг; potassium мг; selenium мкг; sodium мг; zinc мг; omega3 г.
""".strip()


async def interpret_dialog_message(session: AsyncSession, user: User, message_text: str) -> DialogDecision | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    context = await _build_dialog_context(session, user)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_input = (
        f"Контекст дневника:\n{context}\n\n"
        f"Новое сообщение пользовательницы:\n{message_text}\n\n"
        "Верни одно структурированное действие."
    )

    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            instructions=SYSTEM_PROMPT,
            input=user_input,
            text_format=DialogDecision,
        )
        return response.output_parsed
    except Exception as exc:
        logger.warning("dialog responses.parse failed, falling back to JSON schema create: %s", exc)

    try:
        response = await client.responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_PROMPT,
            input=user_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "dialog_decision",
                    "schema": DialogDecision.model_json_schema(),
                    "strict": True,
                }
            },
        )
        return DialogDecision.model_validate(json.loads(response.output_text))
    except Exception as exc:
        logger.exception("dialog interpretation failed: %s", exc)
        return None


async def _build_dialog_context(session: AsyncSession, user: User) -> str:
    report = await build_daily_report(session, user)
    result = await session.execute(
        select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.datetime.desc()).limit(8)
    )
    logs = list(result.scalars().all())
    lines = [
        f"Пользователь: {user.name or user.telegram_id}.",
        f"Цели: {user.calorie_target:.0f} ккал, Б {user.protein_target:.0f} г, "
        f"Ж {user.fat_target:.0f} г, У {user.carb_target:.0f} г.",
        f"Сегодня: {report.calories_fact:.0f}/{report.calories_target:.0f} ккал, "
        f"Б {report.protein_fact:.0f}/{report.protein_target:.0f}, "
        f"Ж {report.fat_fact:.0f}/{report.fat_target:.0f}, "
        f"У {report.carbs_fact:.0f}/{report.carbs_target:.0f}, клетчатка {report.fiber_fact:.0f} г.",
    ]
    if any([report.steps, report.active_calories, report.total_burned_calories, report.sleep_minutes, report.avg_heart_rate]):
        lines.append(
            f"Активность: шаги {report.steps}, активные калории {report.active_calories:.0f}, "
            f"всего потрачено {report.total_burned_calories:.0f}, "
            f"баланс {report.estimated_balance_calories:+.0f} ккал, " if report.estimated_balance_calories is not None else
            f"Активность: шаги {report.steps}, активные калории {report.active_calories:.0f}, "
            f"всего потрачено {report.total_burned_calories:.0f}, "
        )
    if logs:
        lines.append("Последние записи, новые сверху:")
        for log in logs:
            raw = (log.raw_user_input or log.notes or log.meal_type or "приём пищи").replace("\n", " ")[:220]
            lines.append(
                f"- id={log.id}, {log.datetime:%d.%m %H:%M}, {log.source_type}: {raw}; "
                f"{log.calories:.0f} ккал, Б {log.protein:.0f}, Ж {log.fat:.0f}, У {log.carbs:.0f}"
            )
    else:
        lines.append("Последних записей еды нет.")
    return "\n".join(lines)
