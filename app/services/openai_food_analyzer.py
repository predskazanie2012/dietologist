import base64
import json
import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings

logger = logging.getLogger(__name__)


class FoodVisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    amount: str
    grams: float = Field(ge=0)
    calories: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class FoodVisionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    items: list[FoodVisionItem] = Field(default_factory=list)
    total_calories: float = Field(ge=0)
    total_protein: float = Field(ge=0)
    total_fat: float = Field(ge=0)
    total_carbs: float = Field(ge=0)
    total_fiber: float = Field(default=0, ge=0)
    confidence: float = Field(ge=0, le=1)
    notes: str = ""


SYSTEM_PROMPT = """
Ты помогаешь вести оценочный пищевой дневник по фото еды.

Главное правило: для фото верни готовую среднюю оценку приема пищи, а не текст для дальнейшего парсинга.

Как считать:
- Давай одну наиболее вероятную среднюю оценку, без диапазонов min/max.
- Для каждого продукта укажи название, бытовое количество, граммы или мл и ккал.
- БЖУ и клетчатку считай только общим итогом приема пищи в total_*.
- Общие total_* должны быть суммой позиций items.
- Не считай витамины и микроэлементы в фото-ответе. Их считает отдельный недельный анализ.
- Если видишь альтернативы вроде "лосось/красная рыба" или "творог/творожная масса", выбери один наиболее вероятный вариант, не считай оба.
- Неизвестный напиток не считай как сок. Включай напиток в калории только если он очевиден или пользователь уточнил, что это сок/матча/латте/кофе/молоко.
- Если пользователь прислал уточнение к фото, обязательно учитывай его и пересчитай весь прием пищи целиком.
- Если точность низкая, всё равно дай разумную среднюю оценку и снизь confidence. Не задавай вопросы.
- Не ставь медицинские диагнозы, не предлагай лекарства, БАДы или витамины.
""".strip()


async def analyze_food_image(image_bytes: bytes, user_text: str | None = None) -> FoodVisionAnalysis | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    user_prompt = user_text or "Оцени еду на фото для пищевого дневника и сразу посчитай средние КБЖУ."
    content = [
        {"type": "input_text", "text": user_prompt},
        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"},
    ]

    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            reasoning={"effort": "none"},
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": content}],
            text_format=FoodVisionAnalysis,
        )
        return response.output_parsed
    except Exception as exc:
        logger.warning("food vision responses.parse failed, falling back to JSON schema create: %s", exc)

    try:
        schema = FoodVisionAnalysis.model_json_schema()
        response = await client.responses.create(
            model=settings.openai_model,
            reasoning={"effort": "none"},
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": content}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "food_vision_analysis",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        return FoodVisionAnalysis.model_validate(json.loads(response.output_text))
    except Exception as exc:
        logger.exception("food vision analysis failed: %s", exc)
        return None
