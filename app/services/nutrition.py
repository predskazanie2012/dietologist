import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food, MealLog, StandardMeal, StandardMealItem, User
from app.schemas import MICRONUTRIENT_KEYS, NutrientTotals
from app.text import fix_text


MICRO_FIELD_MAP = {
    "magnesium": "magnesium_per_100g",
    "potassium": "potassium_per_100g",
    "calcium": "calcium_per_100g",
    "iron": "iron_per_100g",
    "zinc": "zinc_per_100g",
    "iodine": "iodine_per_100g",
    "selenium": "selenium_per_100g",
    "vitamin_c": "vitamin_c_per_100g",
    "vitamin_a": "vitamin_a_per_100g",
    "vitamin_e": "vitamin_e_per_100g",
    "omega3": "omega3_per_100g",
}

DEFAULT_PORTIONS_G = {
    "яблоко": 150,
    "банан": 120,
    "яйцо": 55,
    "борщ": 300,
    "салат": 180,
    "гречка": 150,
    "перловка": 150,
    "курица": 120,
    "рыба": 130,
    "творог": 150,
    "чечевица": 150,
    "фасоль": 150,
    "шпинат": 80,
    "орехи": 25,
    "оливковое масло": 10,
}
DEFAULT_PORTIONS_G.update(
    {
        "утка": 120,
        "картофель": 180,
        "сметана": 20,
        "песто": 15,
        "виноградный сок": 200,
        "рис": 150,
        "ягоды": 80,
        "зелёный смузи": 200,
    }
)

DEFAULT_PORTIONS_G.update(
    {
        "\u043f\u0440\u043e\u0448\u0443\u0442\u0442\u043e": 30,
        "\u043f\u043e\u0434\u0441\u043e\u043b\u043d\u0435\u0447\u043d\u043e\u0435 \u043c\u0430\u0441\u043b\u043e": 10,
        "\u043c\u0430\u0442\u0447\u0430 \u043b\u0430\u0442\u0442\u0435": 250,
        "\u0441\u0430\u0445\u0430\u0440": 10,
        "\u043c\u043e\u043b\u043e\u043a\u043e": 200,
        "\u0441\u0443\u0448\u043a\u0438": 50,
    }
)

DEFAULT_PORTIONS_G.update(
    {
        "\u043a\u0440\u0435\u0432\u0435\u0442\u043a\u0438": 140,
        "\u0442\u043e\u0444\u0443": 100,
        "\u044d\u0434\u0430\u043c\u0430\u043c\u0435": 80,
        "\u0430\u0432\u043e\u043a\u0430\u0434\u043e": 80,
        "\u0445\u043b\u0435\u0431": 35,
        "\u0431\u0435\u043b\u044b\u0439 \u0445\u043b\u0435\u0431": 35,
        "\u0440\u0436\u0430\u043d\u043e\u0439 \u0445\u043b\u0435\u0431": 35,
        "\u0431\u0430\u0442\u043e\u043d": 35,
        "\u043b\u0430\u0432\u0430\u0448": 50,
        "\u043f\u0435\u0447\u0435\u043d\u044c\u0435": 15,
        "\u043a\u043e\u043d\u0444\u0435\u0442\u0430": 15,
        "\u0441\u044b\u0440\u043d\u0438\u043a\u0438": 70,
        "\u043a\u043e\u0442\u043b\u0435\u0442\u0430": 80,
        "\u0442\u0435\u0444\u0442\u0435\u043b\u0438": 60,
        "\u0441\u043e\u0441\u0438\u0441\u043a\u0430": 50,
        "\u0431\u043b\u0438\u043d\u044b": 70,
        "\u043e\u043b\u0430\u0434\u044c\u0438": 50,
        "\u0430\u043f\u0435\u043b\u044c\u0441\u0438\u043d": 150,
        "\u043c\u0430\u043d\u0434\u0430\u0440\u0438\u043d": 80,
        "\u0433\u0440\u0443\u0448\u0430": 160,
        "\u043f\u043e\u043c\u0438\u0434\u043e\u0440": 100,
        "\u043e\u0433\u0443\u0440\u0435\u0446": 100,
        "\u043a\u0430\u043f\u0443\u0447\u0438\u043d\u043e": 200,
        "\u043a\u043e\u0444\u0435 \u0441 \u043c\u043e\u043b\u043e\u043a\u043e\u043c": 200,
        "\u0447\u0430\u0439 \u0441 \u0441\u0430\u0445\u0430\u0440\u043e\u043c": 200,
        "\u043a\u043e\u043c\u043f\u043e\u0442": 200,
        "\u044f\u0431\u043b\u043e\u0447\u043d\u044b\u0439 \u0441\u043e\u043a": 200,
        "\u0430\u043f\u0435\u043b\u044c\u0441\u0438\u043d\u043e\u0432\u044b\u0439 \u0441\u043e\u043a": 200,
        "\u043a\u0432\u0430\u0441": 200,
    }
)

PIECE_WEIGHTS_G = {
    "\u044f\u0439\u0446\u043e": 55,
    "\u043a\u0440\u0435\u0432\u0435\u0442\u043a\u0438": 12,
    "\u0430\u0432\u043e\u043a\u0430\u0434\u043e": 150,
    "\u0445\u043b\u0435\u0431": 35,
    "\u0431\u0435\u043b\u044b\u0439 \u0445\u043b\u0435\u0431": 35,
    "\u0440\u0436\u0430\u043d\u043e\u0439 \u0445\u043b\u0435\u0431": 35,
    "\u0431\u0430\u0442\u043e\u043d": 35,
    "\u043b\u0430\u0432\u0430\u0448": 50,
    "\u043f\u0435\u0447\u0435\u043d\u044c\u0435": 15,
    "\u043a\u043e\u043d\u0444\u0435\u0442\u0430": 15,
    "\u0441\u043e\u0441\u0438\u0441\u043a\u0430": 50,
}

FOOD_ALIASES = {
    "\u044f\u0439\u0446\u0430": "\u044f\u0439\u0446\u043e",
    "\u044f\u0438\u0446": "\u044f\u0439\u0446\u043e",
    "\u043a\u0440\u0435\u0432\u0435\u0442\u043a\u0430": "\u043a\u0440\u0435\u0432\u0435\u0442\u043a\u0438",
    "\u043a\u0440\u0435\u0432\u0435\u0442\u043e\u043a": "\u043a\u0440\u0435\u0432\u0435\u0442\u043a\u0438",
    "\u044d\u0434\u0430\u043c\u0430\u043c\u044d": "\u044d\u0434\u0430\u043c\u0430\u043c\u0435",
    "\u0441\u043e\u0435\u0432\u044b\u0435 \u0431\u043e\u0431\u044b": "\u044d\u0434\u0430\u043c\u0430\u043c\u0435",
    "\u043f\u0440\u043e\u0448\u0443\u0442\u0442\u043e": "\u043f\u0440\u043e\u0448\u0443\u0442\u0442\u043e",
    "\u0432\u0435\u0442\u0447\u0438\u043d\u0430": "\u043f\u0440\u043e\u0448\u0443\u0442\u0442\u043e",
    "\u0441\u044b\u0440\u043e\u0432\u044f\u043b\u0435\u043d\u043e\u0435 \u043c\u044f\u0441\u043e": "\u043f\u0440\u043e\u0448\u0443\u0442\u0442\u043e",
    "\u043c\u0430\u0441\u043b\u043e": "\u043f\u043e\u0434\u0441\u043e\u043b\u043d\u0435\u0447\u043d\u043e\u0435 \u043c\u0430\u0441\u043b\u043e",
    "\u043c\u0430\u0441\u043b\u043e\u043c": "\u043f\u043e\u0434\u0441\u043e\u043b\u043d\u0435\u0447\u043d\u043e\u0435 \u043c\u0430\u0441\u043b\u043e",
    "\u043f\u043e\u0434\u0441\u043e\u043b\u043d\u0435\u0447\u043d\u044b\u043c \u043c\u0430\u0441\u043b\u043e\u043c": "\u043f\u043e\u0434\u0441\u043e\u043b\u043d\u0435\u0447\u043d\u043e\u0435 \u043c\u0430\u0441\u043b\u043e",
    "\u043c\u0430\u0442\u0447\u0430-\u043b\u0430\u0442\u0442\u0435": "\u043c\u0430\u0442\u0447\u0430 \u043b\u0430\u0442\u0442\u0435",
    "\u043c\u0430\u0442\u0447\u0430 \u043b\u0430\u0442\u0442\u0435": "\u043c\u0430\u0442\u0447\u0430 \u043b\u0430\u0442\u0442\u0435",
    "\u043b\u0430\u0442\u0442\u0435": "\u043c\u0430\u0442\u0447\u0430 \u043b\u0430\u0442\u0442\u0435",
    "\u0441\u0430\u0445\u0430\u0440\u043e\u043c": "\u0441\u0430\u0445\u0430\u0440",
    "\u0441\u0430\u0445\u0430\u0440\u0430": "\u0441\u0430\u0445\u0430\u0440",
    "\u0441\u0430\u043b\u0430\u0442\u0430": "\u0441\u0430\u043b\u0430\u0442",
    "\u043e\u0432\u043e\u0449\u043d\u043e\u0439 \u0441\u0430\u043b\u0430\u0442": "\u0441\u0430\u043b\u0430\u0442",
    "гречневая": "гречка",
    "гречневая каша": "гречка",
    "каша гречневая": "гречка",
    "\u043f\u0435\u0440\u043b\u043e\u0432\u0430\u044f \u043a\u0440\u0443\u043f\u0430": "\u043f\u0435\u0440\u043b\u043e\u0432\u043a\u0430",
    "\u043f\u0435\u0440\u043b\u043e\u0432\u043e\u0439 \u043a\u0440\u0443\u043f\u044b": "\u043f\u0435\u0440\u043b\u043e\u0432\u043a\u0430",
    "\u0444\u0430\u0441\u043e\u043b\u0438": "\u0444\u0430\u0441\u043e\u043b\u044c",
    "\u0444\u0430\u0441\u043e\u043b\u044c\u044e": "\u0444\u0430\u0441\u043e\u043b\u044c",
    "\u043a\u0443\u0440\u0438\u0446\u044b": "\u043a\u0443\u0440\u0438\u0446\u0430",
    "\u043a\u0443\u0440\u0438\u0446\u0435\u0439": "\u043a\u0443\u0440\u0438\u0446\u0430",
    "\u043a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044f": "\u043a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c",
    "\u0431\u043e\u0440\u0449\u0435": "\u0431\u043e\u0440\u0449",
    "\u0441\u0443\u043f": "\u0431\u043e\u0440\u0449",
    "\u043c\u043e\u043b\u043e\u043a\u0430": "\u043c\u043e\u043b\u043e\u043a\u043e",
    "\u043c\u043e\u043b\u043e\u043a\u043e\u043c": "\u043c\u043e\u043b\u043e\u043a\u043e",
    "\u0441\u0442\u0430\u043a\u0430\u043d \u043c\u043e\u043b\u043e\u043a\u0430": "\u043c\u043e\u043b\u043e\u043a\u043e",
    "\u0441\u0443\u0448\u0435\u043a": "\u0441\u0443\u0448\u043a\u0438",
    "\u0441\u0443\u0448\u043a\u0430": "\u0441\u0443\u0448\u043a\u0438",
    "\u0441\u0443\u0448\u043a\u0443": "\u0441\u0443\u0448\u043a\u0438",
    "\u0441\u044b\u0440\u043d\u0438\u043a": "\u0441\u044b\u0440\u043d\u0438\u043a\u0438",
    "\u0441\u044b\u0440\u043d\u0438\u043a\u0430": "\u0441\u044b\u0440\u043d\u0438\u043a\u0438",
    "\u0441\u044b\u0440\u043d\u0438\u043a\u0443": "\u0441\u044b\u0440\u043d\u0438\u043a\u0438",
    "\u0441\u044b\u0440\u043d\u0438\u043a\u043e\u043c": "\u0441\u044b\u0440\u043d\u0438\u043a\u0438",
    "\u043f\u0435\u0447\u0435\u043d\u044c\u044f": "\u043f\u0435\u0447\u0435\u043d\u044c\u0435",
    "\u043f\u0435\u0447\u0435\u043d\u044e\u0448\u043a\u0430": "\u043f\u0435\u0447\u0435\u043d\u044c\u0435",
    "\u043f\u0435\u0447\u0435\u043d\u044e\u0448\u043a\u0438": "\u043f\u0435\u0447\u0435\u043d\u044c\u0435",
    "\u043a\u0443\u0441\u043e\u043a \u0445\u043b\u0435\u0431\u0430": "\u0445\u043b\u0435\u0431",
    "\u043b\u043e\u043c\u0442\u0438\u043a \u0445\u043b\u0435\u0431\u0430": "\u0445\u043b\u0435\u0431",
}

MEAL_WORDS = {
    "завтрак": "breakfast",
    "утро": "breakfast",
    "обед": "lunch",
    "день": "lunch",
    "ужин": "dinner",
    "вечер": "dinner",
    "перекус": "snack",
}


@dataclass
class ParsedFoodItem:
    food: Food
    grams: float


def empty_micros() -> dict[str, float]:
    return {key: 0.0 for key in MICRONUTRIENT_KEYS}


def add_totals(left: NutrientTotals, right: NutrientTotals) -> NutrientTotals:
    micros = empty_micros()
    for key in micros:
        micros[key] = left.micronutrients.get(key, 0) + right.micronutrients.get(key, 0)
    return NutrientTotals(
        calories=left.calories + right.calories,
        protein=left.protein + right.protein,
        fat=left.fat + right.fat,
        carbs=left.carbs + right.carbs,
        fiber=left.fiber + right.fiber,
        micronutrients=micros,
    )


def calculate_food(food: Food, grams: float) -> NutrientTotals:
    factor = grams / 100
    return NutrientTotals(
        calories=food.calories_per_100g * factor,
        protein=food.protein_per_100g * factor,
        fat=food.fat_per_100g * factor,
        carbs=food.carbs_per_100g * factor,
        fiber=food.fiber_per_100g * factor,
        micronutrients={
            key: float(getattr(food, field, 0) or 0) * factor
            for key, field in MICRO_FIELD_MAP.items()
        },
    )


def calculate_items(items: list[ParsedFoodItem]) -> NutrientTotals:
    total = NutrientTotals(micronutrients=empty_micros())
    for item in items:
        total = add_totals(total, calculate_food(item.food, item.grams))
    return total


def infer_meal_type(text: str) -> str | None:
    lowered = _searchable_text(text)
    for word, meal_type in MEAL_WORDS.items():
        if _searchable_text(word) in lowered:
            return meal_type
    hour = datetime.now().hour
    if hour < 11:
        return "breakfast"
    if hour < 16:
        return "lunch"
    if hour < 22:
        return "dinner"
    return "snack"


def _searchable_text(text: str) -> str:
    return fix_text(text).lower().replace("ё", "е")


def _default_portion(food_name: str) -> float:
    food_key = _searchable_text(food_name)
    food_key = _searchable_text(FOOD_ALIASES.get(food_key, food_key))
    for key, grams in DEFAULT_PORTIONS_G.items():
        key_text = _searchable_text(key)
        if key_text == food_key or food_key in _name_variants(key_text):
            return grams
    return 100


def _piece_weight(food_name: str) -> float:
    food_key = _searchable_text(food_name)
    food_key = _searchable_text(FOOD_ALIASES.get(food_key, food_key))
    for key, grams in PIECE_WEIGHTS_G.items():
        key_text = _searchable_text(key)
        if key_text == food_key or food_key in _name_variants(key_text):
            return grams
    return _default_portion(food_name)


def _is_orphan_amount_fragment(fragment: str) -> bool:
    return bool(
        re.fullmatch(
            r"[\s~≈.,;:()/-]*\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?\s*"
            r"(?:г|гр|грамм(?:а|ов)?|g|мл|ml)\.?",
            _searchable_text(fragment),
        )
    )


def _split_food_fragments(text: str) -> list[str]:
    lowered = re.sub(r"\s+", " ", _searchable_text(text))
    raw_parts = [part.strip() for part in re.split(r"[,;\n]+|\s+\+\s+", lowered) if part.strip()]
    parts: list[str] = []
    for part in raw_parts:
        if parts and (
            _is_orphan_amount_fragment(part)
            or part.startswith(("вероятно ", "похоже ", "скорее "))
        ):
            parts[-1] = f"{parts[-1]}, {part}"
        else:
            parts.append(part)
    return parts


def _number_value(match: re.Match[str]) -> float:
    return float(match.group(1).replace(",", "."))


def _number_text_value(value: str) -> float:
    return float(value.replace(",", "."))


def _explicit_grams_from_text(text: str) -> float | None:
    unit = r"(?:г|гр|грамм(?:а|ов)?|g|мл|ml)"
    range_match = re.search(
        rf"(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*{unit}\b",
        text,
    )
    if range_match:
        return (_number_text_value(range_match.group(1)) + _number_text_value(range_match.group(2))) / 2

    single_match = re.search(rf"(\d+(?:[.,]\d+)?)\s*{unit}\b", text)
    if single_match:
        return _number_value(single_match)

    return None


def _fractional_piece_count(text: str) -> float | None:
    range_match = re.search(
        r"(\d+)\s*/\s*(\d+)\s*[-–—]\s*(\d+)\s*/\s*(\d+)\s*(?:шт|штук)",
        text,
    )
    if range_match:
        left = int(range_match.group(1)) / int(range_match.group(2))
        right = int(range_match.group(3)) / int(range_match.group(4))
        return (left + right) / 2

    single_match = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:шт|штук)", text)
    if single_match:
        return int(single_match.group(1)) / int(single_match.group(2))

    return None


def _estimate_grams(fragment: str, food_name: str) -> float:
    lowered = _searchable_text(fragment)
    grams_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:г|гр|грамм(?:а|ов)?|g)\b", lowered)
    if grams_match:
        return _number_value(grams_match)

    spoon_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ложк|ст\.?\s*л)", lowered)
    if spoon_match:
        return _number_value(spoon_match) * 20

    plate_match = re.search(r"(\d+(?:[.,]\d+)?)?\s*(?:тарелк|порци)", lowered)
    if plate_match:
        count = float((plate_match.group(1) or "1").replace(",", "."))
        return count * 300

    piece_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:шт|штук)", lowered)
    if piece_match:
        return _number_value(piece_match) * _default_portion(food_name)

    food_pattern = re.escape(_searchable_text(food_name))
    bare_after_food = re.search(rf"{food_pattern}\D{{0,18}}(\d+(?:[.,]\d+)?)\b", lowered)
    if bare_after_food:
        return _number_value(bare_after_food)

    return _default_portion(food_name)


def _estimate_grams(fragment: str, food_name: str) -> float:
    lowered = _searchable_text(fragment)
    canonical_food_name = _searchable_text(FOOD_ALIASES.get(_searchable_text(food_name), food_name))
    if canonical_food_name == "\u043a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c" and "\u043a\u0443\u0441\u043e\u0447" in lowered:
        return 80
    if canonical_food_name == "\u043c\u043e\u043b\u043e\u043a\u043e" and "\u0441\u0442\u0430\u043a\u0430\u043d" in lowered:
        return 200

    explicit_grams = _explicit_grams_from_text(lowered)
    if explicit_grams is not None:
        grams = explicit_grams
        if "масло" in canonical_food_name and grams > 50:
            return _default_portion(food_name)
        return grams

    spoon_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:\u043b\u043e\u0436\u043a|\u0441\u0442\.?\s*\u043b)", lowered)
    if spoon_match:
        return _number_value(spoon_match) * 20

    glass_match = re.search(r"(\d+(?:[.,]\d+)?)?\s*(?:\u0441\u0442\u0430\u043a\u0430\u043d)", lowered)
    if glass_match:
        count = float((glass_match.group(1) or "1").replace(",", "."))
        return count * 200

    plate_match = re.search(r"(\d+(?:[.,]\d+)?)?\s*(?:\u0442\u0430\u0440\u0435\u043b\u043a|\u043f\u043e\u0440\u0446\u0438)", lowered)
    if plate_match:
        count = float((plate_match.group(1) or "1").replace(",", "."))
        return count * 300

    bowl_match = re.search(r"(\d+(?:[.,]\d+)?)?\s*(?:\u043c\u0438\u0441\u043a|\u043a\u0440\u0443\u0436\u043a|\u0447\u0430\u0448\u043a)", lowered)
    if bowl_match:
        count = float((bowl_match.group(1) or "1").replace(",", "."))
        return count * 300

    fractional_piece_count = _fractional_piece_count(lowered)
    if fractional_piece_count is not None:
        return fractional_piece_count * _piece_weight(food_name)

    piece_range_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*"
        r"(?:\u0448\u0442|\u0448\u0442\u0443\u043a|\u043a\u0443\u0441\u043e\u043a|\u043a\u0443\u0441\u043a|\u043b\u043e\u043c\u0442\u0438\u043a)",
        lowered,
    )
    if piece_range_match:
        count = (_number_text_value(piece_range_match.group(1)) + _number_text_value(piece_range_match.group(2))) / 2
        return count * _piece_weight(food_name)

    piece_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:\u0448\u0442|\u0448\u0442\u0443\u043a|\u043a\u0443\u0441\u043e\u043a|\u043a\u0443\u0441\u043a|\u043b\u043e\u043c\u0442\u0438\u043a)", lowered)
    if piece_match:
        return _number_value(piece_match) * _piece_weight(food_name)

    food_pattern = re.escape(_searchable_text(food_name))
    if canonical_food_name == "\u044f\u0439\u0446\u043e":
        egg_count = re.search(r"(\d+(?:[.,]\d+)?)\s*\u044f\u0439\u0446\w*", lowered)
        if egg_count:
            return _number_value(egg_count) * _default_portion("\u044f\u0439\u0446\u043e")

    count_before_food = re.search(rf"(\d+(?:[.,]\d+)?)\s*(?:{food_pattern})\w*", lowered)
    if count_before_food and _default_portion(food_name) <= 80:
        return _number_value(count_before_food) * _default_portion(food_name)

    bare_after_food = re.search(rf"{food_pattern}\D{{0,18}}(\d+(?:[.,]\d+)?)\b", lowered)
    if bare_after_food:
        return _number_value(bare_after_food)

    return _default_portion(food_name)


def _is_negated_mention(text: str, start: int, food_name: str) -> bool:
    before = text[max(0, start - 24):start]
    after = text[start:start + len(food_name) + 24]
    if re.search(r"(?:не|нет|без|никак(?:ой|ая|ое|ие)?)\s+(?:\w+\s+)?$", before):
        return True
    return bool(re.search(r"^\w*\s*(?:не было|нет|практически не было)", after))


def _name_variants(name: str) -> set[str]:
    name = _searchable_text(name)
    variants = {name}
    if " " in name:
        return variants

    if name.endswith("а"):
        stem = name[:-1]
        variants.update({stem + ending for ending in ("ы", "е", "у", "ой", "ою")})
    elif name.endswith("я"):
        stem = name[:-1]
        variants.update({stem + ending for ending in ("и", "е", "ю", "ей")})
    elif name.endswith("о"):
        stem = name[:-1]
        variants.update({stem + ending for ending in ("а", "ом", "у")})
    elif name.endswith("е"):
        stem = name[:-1]
        variants.update({stem + ending for ending in ("я", "ем", "ю")})
    elif name.endswith("ь"):
        stem = name[:-1]
        variants.update({stem + ending for ending in ("я", "ю", "ем", "и", "ью")})
    elif name.endswith("ы") or name.endswith("и"):
        stem = name[:-1]
        variants.update({stem + ending for ending in ("", "ов", "ами", "ах")})
        if name.endswith("ки"):
            variants.add(name[:-2] + "ек")
        if name.endswith("ики"):
            singular = name[:-1]
            variants.update({singular, singular + "а", singular + "у", singular + "ом", singular + "е"})
    else:
        variants.update({name + ending for ending in ("а", "у", "ом", "е")})

    return {variant for variant in variants if len(variant) >= 3}


def _food_mentions(segment: str, foods: list[Food]) -> list[tuple[int, int, Food, str]]:
    mentions: list[tuple[int, int, Food, str]] = []
    occupied: list[tuple[int, int]] = []
    for food in sorted(foods, key=lambda item: len(item.name), reverse=True):
        name = _searchable_text(food.name)
        pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
        for match in re.finditer(pattern, segment):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            occupied.append((start, end))
            mentions.append((start, end, food, name))
    return sorted(mentions, key=lambda item: item[0])


GENERIC_FOOD_COVERED_BY_SPECIFIC = {
    "\u0440\u044b\u0431\u0430": {
        "\u043b\u043e\u0441\u043e\u0441\u044c",
        "\u0441\u0435\u043c\u0433\u0430",
        "\u0441\u0451\u043c\u0433\u0430",
        "\u0442\u0443\u043d\u0435\u0446",
        "\u0441\u043a\u0443\u043c\u0431\u0440\u0438\u044f",
        "\u0441\u0435\u043b\u044c\u0434\u044c",
    },
}


def _filter_food_mentions(segment: str, mentions: list[tuple[int, int, Food, str]]) -> list[tuple[int, int, Food, str]]:
    present_names = {_searchable_text(food.name) for _, _, food, _ in mentions}
    filtered: list[tuple[int, int, Food, str]] = []
    for start, end, food, name in mentions:
        canonical_name = _searchable_text(food.name)
        covered_by = GENERIC_FOOD_COVERED_BY_SPECIFIC.get(canonical_name)
        if covered_by and present_names.intersection(covered_by):
            continue
        if segment[max(0, start - 2):start].strip().endswith(("/", "\\")):
            continue
        if filtered and "или" in segment[filtered[-1][1]:start]:
            continue
        if canonical_name == "семечки" and re.search(r"(?:хлеб|булоч)\w*[^,;]{0,40}\sс\s+семеч", segment):
            continue
        filtered.append((start, end, food, name))
    return filtered


def _food_mentions(segment: str, foods: list[Food]) -> list[tuple[int, int, Food, str]]:
    mentions: list[tuple[int, int, Food, str]] = []
    occupied: list[tuple[int, int]] = []
    food_by_name = {_searchable_text(food.name): food for food in foods}
    candidates: list[tuple[str, Food]] = [(name, food) for name, food in food_by_name.items()]
    for name, food in food_by_name.items():
        for variant in _name_variants(name):
            candidates.append((variant, food))

    for alias, canonical in FOOD_ALIASES.items():
        food = food_by_name.get(_searchable_text(canonical))
        if food is not None:
            candidates.append((_searchable_text(alias), food))

    for name, food in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
        for match in re.finditer(pattern, segment):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            occupied.append((start, end))
            mentions.append((start, end, food, name))
    return _filter_food_mentions(segment, sorted(mentions, key=lambda item: item[0]))


async def find_known_foods(session: AsyncSession) -> list[Food]:
    result = await session.execute(select(Food).order_by(Food.name))
    return list(result.scalars().all())


async def parse_food_text(session: AsyncSession, text: str) -> list[ParsedFoodItem]:
    foods = await find_known_foods(session)
    items: list[ParsedFoodItem] = []
    for segment in _split_food_fragments(text):
        mentions = _food_mentions(segment, foods)
        seen_food_ids: set[int] = set()
        for index, (start, end, food, name) in enumerate(mentions):
            if food.id in seen_food_ids or _is_negated_mention(segment, start, name):
                continue
            next_start = mentions[index + 1][0] if index + 1 < len(mentions) else len(segment)
            fragment_start = max(0, start - 16)
            fragment = segment[fragment_start:next_start]
            items.append(ParsedFoodItem(food=food, grams=_estimate_grams(fragment, name)))
            seen_food_ids.add(food.id)
    return items


async def log_food_text(session: AsyncSession, user: User, text: str, source_type: str = "text") -> MealLog | None:
    items = await parse_food_text(session, text)
    if not items:
        return None
    totals = calculate_items(items)
    meal_log = MealLog(
        user_id=user.id,
        datetime=datetime.now(ZoneInfo(user.timezone)),
        meal_type=infer_meal_type(text),
        source_type=source_type,
        raw_user_input=text,
        calories=totals.calories,
        protein=totals.protein,
        fat=totals.fat,
        carbs=totals.carbs,
        fiber=totals.fiber,
        micronutrients_json=totals.micronutrients,
        confidence=0.8,
        notes=", ".join(f"{item.food.name} {item.grams:.0f} г" for item in items),
    )
    session.add(meal_log)
    await session.commit()
    await session.refresh(meal_log)
    return meal_log


def normalize_standard_meal_name(value: str) -> str:
    normalized = value.lower().replace("ё", "е").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[\s:;.,!?—-]+$", "", normalized)
    return normalized


async def find_standard_meal(session: AsyncSession, user: User, text: str) -> StandardMeal | None:
    normalized_text = normalize_standard_meal_name(text)
    if not normalized_text:
        return None
    result = await session.execute(
        select(StandardMeal).where(StandardMeal.user_id == user.id)
    )
    meals = list(result.scalars().all())
    for meal in meals:
        if normalize_standard_meal_name(meal.name) == normalized_text:
            return meal
    return None


async def log_standard_meal(session: AsyncSession, user: User, meal: StandardMeal, raw_user_input: str) -> MealLog:
    meal_log = MealLog(
        user_id=user.id,
        datetime=datetime.now(ZoneInfo(user.timezone)),
        meal_type=infer_meal_type(meal.name),
        source_type="standard_meal",
        standard_meal_id=meal.id,
        raw_user_input=raw_user_input,
        calories=meal.total_calories,
        protein=meal.total_protein,
        fat=meal.total_fat,
        carbs=meal.total_carbs,
        fiber=meal.total_fiber,
        micronutrients_json=meal.micronutrients_json or empty_micros(),
        confidence=1.0,
        notes=meal.description,
    )
    session.add(meal_log)
    await session.commit()
    await session.refresh(meal_log)
    return meal_log


async def create_standard_meal_from_text(session: AsyncSession, user: User, name: str, ingredients_text: str) -> StandardMeal | None:
    items = await parse_food_text(session, ingredients_text)
    if not items:
        return None
    normalized_name = normalize_standard_meal_name(name)
    if not normalized_name:
        return None
    totals = calculate_items(items)
    return await save_standard_meal_from_totals(
        session,
        user,
        normalized_name,
        ", ".join(f"{item.food.name} {item.grams:.0f} г" for item in items),
        totals.calories,
        totals.protein,
        totals.fat,
        totals.carbs,
        totals.fiber,
        totals.micronutrients,
        items,
    )


async def save_standard_meal_from_totals(
    session: AsyncSession,
    user: User,
    name: str,
    description: str,
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
    fiber: float = 0,
    micronutrients_json: dict | None = None,
    items: list[ParsedFoodItem] | None = None,
) -> StandardMeal | None:
    normalized_name = normalize_standard_meal_name(name)
    if not normalized_name or calories <= 0:
        return None

    result = await session.execute(
        select(StandardMeal)
        .where(StandardMeal.user_id == user.id, StandardMeal.name == normalized_name)
        .order_by(StandardMeal.id.desc())
        .limit(1)
    )
    meal = result.scalar_one_or_none()
    if meal is None:
        meal = StandardMeal(user_id=user.id, name=normalized_name)
        session.add(meal)
        await session.flush()
    else:
        await session.execute(delete(StandardMealItem).where(StandardMealItem.standard_meal_id == meal.id))

    meal.description = description
    meal.total_calories = calories
    meal.total_protein = protein
    meal.total_fat = fat
    meal.total_carbs = carbs
    meal.total_fiber = fiber
    meal.micronutrients_json = micronutrients_json or empty_micros()

    for item in items or []:
        session.add(StandardMealItem(standard_meal_id=meal.id, food_id=item.food.id, grams=item.grams))
    await session.commit()
    await session.refresh(meal)
    return meal


def format_logged_meal(meal_log: MealLog, prefix: str = "Записал") -> str:
    name = meal_log.raw_user_input or meal_log.meal_type or "приём пищи"
    return fix_text(
        f"{prefix}: {name} — {meal_log.calories:.0f} ккал, "
        f"белок {meal_log.protein:.0f} г, жиры {meal_log.fat:.0f} г, "
        f"углеводы {meal_log.carbs:.0f} г."
    )
