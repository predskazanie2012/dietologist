import json
import logging
from hashlib import sha256

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.models import MealLog
from app.schemas import MICRONUTRIENT_KEYS
from app.text import normalize_public_nutrition_terms

logger = logging.getLogger(__name__)
WeeklyAnalysis = tuple[dict[str, float], list[str], dict[str, object]]
_CACHE: dict[str, WeeklyAnalysis] = {}


class WeeklyNutrientEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vitamin_a: float = Field(default=0, ge=0)
    vitamin_c: float = Field(default=0, ge=0)
    vitamin_d: float = Field(default=0, ge=0)
    vitamin_e: float = Field(default=0, ge=0)
    vitamin_k: float = Field(default=0, ge=0)
    thiamin: float = Field(default=0, ge=0)
    riboflavin: float = Field(default=0, ge=0)
    niacin: float = Field(default=0, ge=0)
    pantothenic_acid: float = Field(default=0, ge=0)
    vitamin_b6: float = Field(default=0, ge=0)
    biotin: float = Field(default=0, ge=0)
    folate: float = Field(default=0, ge=0)
    vitamin_b12: float = Field(default=0, ge=0)
    choline: float = Field(default=0, ge=0)
    calcium: float = Field(default=0, ge=0)
    chloride: float = Field(default=0, ge=0)
    chromium: float = Field(default=0, ge=0)
    copper: float = Field(default=0, ge=0)
    fluoride: float = Field(default=0, ge=0)
    iodine: float = Field(default=0, ge=0)
    iron: float = Field(default=0, ge=0)
    magnesium: float = Field(default=0, ge=0)
    manganese: float = Field(default=0, ge=0)
    molybdenum: float = Field(default=0, ge=0)
    phosphorus: float = Field(default=0, ge=0)
    potassium: float = Field(default=0, ge=0)
    selenium: float = Field(default=0, ge=0)
    sodium: float = Field(default=0, ge=0)
    zinc: float = Field(default=0, ge=0)
    omega3: float = Field(default=0, ge=0)
    recommendations: list[str] = Field(default_factory=list, max_length=5)
    glycemic_score: float = Field(default=0, ge=0, le=10)
    glycemic_comment: str = Field(default="", max_length=180)
    inflammation_score: float = Field(default=0, ge=0, le=10)
    inflammation_comment: str = Field(default="", max_length=180)
    acid_base_score: float = Field(default=0, ge=0, le=10)
    acid_base_comment: str = Field(default="", max_length=180)


SYSTEM_PROMPT = """
Ты оцениваешь недельный баланс витаминов и микроэлементов по пищевому дневнику.

Правила:
- Верни суммарную оценку за 7 дней, не дневные средние.
- Используй продукты, бытовые порции, граммы и уже записанные КБЖУ как контекст.
- Если точных данных нет, оцени реалистично по типичным пищевым таблицам.
- Это оценочный дневник, не медицинская диагностика.
- Не давай длинных объяснений, верни только структурированные числа и короткие продуктовые recommendations.
- Единицы: vitamin_a мкг RAE; vitamin_c мг; vitamin_d мкг; vitamin_e мг; vitamin_k мкг; thiamin мг; riboflavin мг; niacin мг NE; pantothenic_acid мг; vitamin_b6 мг; biotin мкг; folate мкг DFE; vitamin_b12 мкг; choline мг; calcium мг; chloride мг; chromium мкг; copper мг; fluoride мг; iodine мкг; iron мг; magnesium мг; manganese мг; molybdenum мкг; phosphorus мг; potassium мг; selenium мкг; sodium мг; zinc мг; omega3 г.
- recommendations: 3-5 коротких строк на русском языке.
- В recommendations предлагай только обычные продукты и блюда, без БАДов, витаминных комплексов, порошков и лекарств.
- Подбирай продукты так, чтобы один пункт закрывал сразу 3-5 или больше недостающих микронутриентов.
- Учитывай КБЖУ из контекста: при переборе калорий/жиров выбирай умеренные порции, при недоборе белка добавляй белковые продукты.
- Не предлагай продукты с очень высоким натрием, если sodium уже в переборе.
- Формат строки recommendations: "Продукт/порция/частота - закрывает: нутриент 1, нутриент 2, нутриент 3; зачем: коротко".
""".strip()

SYSTEM_PROMPT = "\n".join(
    (
        SYSTEM_PROMPT,
        """
- Оцени glycemic_score по шкале 1-10: 10 = низкая и стабильная гликемическая нагрузка, много клетчатки, цельных круп, бобовых, овощей и ягод; 1 = много сахара, соков, сладкой выпечки, белого хлеба или рафинированных углеводов.
- Оцени inflammation_score по шкале 1-10: 10 = противовоспалительный профиль питания: рыба/омега-3, овощи, зелень, ягоды, бобовые, орехи, оливковое масло, мало ультрапереработанных продуктов, сахара и переработанного мяса; 1 = выраженно провоспалительный профиль.
- Оцени acid_base_score по шкале 1-10: 10 = хорошая доля овощей, фруктов, зелени, картофеля и бобовых; 1 = высокая кислотная нагрузка: много мяса, сыра, яиц и рафинированных круп при малом количестве овощей.
- glycemic_comment, inflammation_comment, acid_base_comment пиши только на русском, коротко, по одной строке.
- В recommendations учитывай эти 3 фактора: выбирай продукты с низкой/умеренной гликемической нагрузкой, противовоспалительным профилем и поддержкой кислотно-щелочного баланса.
- Не используй слово "гликемия" в пользовательских текстах. Пиши "уровень сахара", "скачки сахара" или "гликемическая нагрузка".
- Если в запросе указан период не 7 дней, оценивай суммарные нутриенты именно за этот фактический период, а не за 7 дней.
""".strip(),
    )
)


def _meal_lines(logs: list[MealLog]) -> str:
    lines: list[str] = []
    for log in logs:
        raw = (log.raw_user_input or log.notes or log.meal_type or "приём пищи").replace("\n", "; ")
        notes = (log.notes or "").replace("\n", "; ")
        if notes and notes != raw:
            raw = f"{raw}; состав: {notes}"
        lines.append(
            f"- {log.datetime:%d.%m %H:%M}: {raw}; "
            f"{log.calories:.0f} ккал, Б {log.protein:.0f} г, Ж {log.fat:.0f} г, "
            f"У {log.carbs:.0f} г, клетчатка {log.fiber:.0f} г"
        )
    return "\n".join(lines)


def _clamp_score(value: object) -> int:
    try:
        number = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, number))


def _normalize_estimate(estimate: WeeklyNutrientEstimate) -> WeeklyAnalysis:
    values = estimate.model_dump()
    micros = {key: float(values.get(key, 0) or 0) for key in MICRONUTRIENT_KEYS}
    recommendations = [
        normalize_public_nutrition_terms(item.strip())
        for item in values.get("recommendations", [])
        if isinstance(item, str) and item.strip()
    ][:5]
    factors = {
        "glycemic_score": _clamp_score(values.get("glycemic_score")),
        "glycemic_comment": normalize_public_nutrition_terms(str(values.get("glycemic_comment", "") or "").strip())[:180],
        "inflammation_score": _clamp_score(values.get("inflammation_score")),
        "inflammation_comment": normalize_public_nutrition_terms(str(values.get("inflammation_comment", "") or "").strip())[:180],
        "acid_base_score": _clamp_score(values.get("acid_base_score")),
        "acid_base_comment": normalize_public_nutrition_terms(str(values.get("acid_base_comment", "") or "").strip())[:180],
    }
    return micros, recommendations, factors


async def analyze_weekly_nutrition(
    logs: list[MealLog],
    nutrition_context: str = "",
    period_days: int = 7,
) -> WeeklyAnalysis | None:
    settings = get_settings()
    if not logs or not settings.openai_api_key:
        return None

    meal_lines = _meal_lines(logs)
    cache_key = sha256(f"{period_days}\n{nutrition_context}\n{meal_lines}".encode("utf-8")).hexdigest()
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_input = (
        f"{nutrition_context}\n\n"
        f"Пищевой дневник за {period_days} дней:\n"
        f"{meal_lines}\n\n"
        "После оценки чисел обязательно заполни recommendations: реальные продукты на следующий период, "
        "которые закрывают главные дефициты микроэлементов и подходят по КБЖУ. "
        f"Оцени суммарные витамины и микроэлементы за эти {period_days} дней."
    )

    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            reasoning={"effort": "none"},
            instructions=SYSTEM_PROMPT,
            input=user_input,
            text_format=WeeklyNutrientEstimate,
        )
        estimate = _normalize_estimate(response.output_parsed)
        _CACHE[cache_key] = estimate
        return estimate
    except Exception as exc:
        logger.warning("weekly nutrient responses.parse failed, falling back to JSON schema create: %s", exc)

    try:
        response = await client.responses.create(
            model=settings.openai_model,
            reasoning={"effort": "none"},
            instructions=SYSTEM_PROMPT,
            input=user_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "weekly_nutrient_estimate",
                    "schema": WeeklyNutrientEstimate.model_json_schema(),
                    "strict": True,
                }
            },
        )
        estimate = _normalize_estimate(WeeklyNutrientEstimate.model_validate(json.loads(response.output_text)))
        _CACHE[cache_key] = estimate
        return estimate
    except Exception as exc:
        logger.exception("weekly nutrient analysis failed: %s", exc)
        return None


async def estimate_weekly_micronutrients(logs: list[MealLog]) -> dict[str, float] | None:
    analysis = await analyze_weekly_nutrition(logs)
    if analysis is None:
        return None
    micros, _, _ = analysis
    return micros
