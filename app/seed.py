import asyncio
import logging

from sqlalchemy import select

from app.database import async_session_maker
from app.models import Food
from app.typical_foods import TYPICAL_FOODS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SEED_FOODS = [
    {
        "name": "яйцо",
        "calories_per_100g": 155,
        "protein_per_100g": 13,
        "fat_per_100g": 11,
        "carbs_per_100g": 1.1,
        "fiber_per_100g": 0,
        "magnesium_per_100g": 12,
        "potassium_per_100g": 126,
        "calcium_per_100g": 50,
        "iron_per_100g": 1.2,
        "zinc_per_100g": 1.0,
        "iodine_per_100g": 49,
        "selenium_per_100g": 30,
        "vitamin_c_per_100g": 0,
        "vitamin_a_per_100g": 160,
        "vitamin_e_per_100g": 1.1,
        "omega3_per_100g": 0.1,
    },
    {"name": "гречка", "calories_per_100g": 110, "protein_per_100g": 3.6, "fat_per_100g": 1.1, "carbs_per_100g": 21, "fiber_per_100g": 2.7, "magnesium_per_100g": 51, "potassium_per_100g": 88, "calcium_per_100g": 7, "iron_per_100g": 0.8, "zinc_per_100g": 0.6, "iodine_per_100g": 0, "selenium_per_100g": 2, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.02},
    {"name": "перловка", "calories_per_100g": 123, "protein_per_100g": 2.3, "fat_per_100g": 0.4, "carbs_per_100g": 28, "fiber_per_100g": 3.8, "magnesium_per_100g": 22, "potassium_per_100g": 54, "calcium_per_100g": 11, "iron_per_100g": 1.3, "zinc_per_100g": 0.8, "iodine_per_100g": 0, "selenium_per_100g": 8, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.02},
    {"name": "курица", "calories_per_100g": 165, "protein_per_100g": 31, "fat_per_100g": 3.6, "carbs_per_100g": 0, "fiber_per_100g": 0, "magnesium_per_100g": 29, "potassium_per_100g": 256, "calcium_per_100g": 15, "iron_per_100g": 1.0, "zinc_per_100g": 1.0, "iodine_per_100g": 5, "selenium_per_100g": 27, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 13, "vitamin_e_per_100g": 0.3, "omega3_per_100g": 0.05},
    {"name": "рыба", "calories_per_100g": 180, "protein_per_100g": 20, "fat_per_100g": 11, "carbs_per_100g": 0, "fiber_per_100g": 0, "magnesium_per_100g": 30, "potassium_per_100g": 360, "calcium_per_100g": 20, "iron_per_100g": 0.6, "zinc_per_100g": 0.7, "iodine_per_100g": 50, "selenium_per_100g": 36, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 35, "vitamin_e_per_100g": 1.0, "omega3_per_100g": 1.5},
    {"name": "творог", "calories_per_100g": 121, "protein_per_100g": 17, "fat_per_100g": 5, "carbs_per_100g": 2, "fiber_per_100g": 0, "magnesium_per_100g": 23, "potassium_per_100g": 112, "calcium_per_100g": 120, "iron_per_100g": 0.3, "zinc_per_100g": 0.4, "iodine_per_100g": 9, "selenium_per_100g": 10, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 55, "vitamin_e_per_100g": 0.2, "omega3_per_100g": 0.03},
    {"name": "борщ", "calories_per_100g": 55, "protein_per_100g": 2.5, "fat_per_100g": 2.0, "carbs_per_100g": 6.5, "fiber_per_100g": 1.8, "magnesium_per_100g": 14, "potassium_per_100g": 170, "calcium_per_100g": 22, "iron_per_100g": 0.6, "zinc_per_100g": 0.3, "iodine_per_100g": 1, "selenium_per_100g": 1, "vitamin_c_per_100g": 8, "vitamin_a_per_100g": 60, "vitamin_e_per_100g": 0.5, "omega3_per_100g": 0.02},
    {"name": "салат", "calories_per_100g": 35, "protein_per_100g": 1.5, "fat_per_100g": 1.0, "carbs_per_100g": 5, "fiber_per_100g": 2.0, "magnesium_per_100g": 18, "potassium_per_100g": 220, "calcium_per_100g": 35, "iron_per_100g": 0.8, "zinc_per_100g": 0.3, "iodine_per_100g": 1, "selenium_per_100g": 1, "vitamin_c_per_100g": 20, "vitamin_a_per_100g": 120, "vitamin_e_per_100g": 0.8, "omega3_per_100g": 0.05},
    {"name": "яблоко", "calories_per_100g": 52, "protein_per_100g": 0.3, "fat_per_100g": 0.2, "carbs_per_100g": 14, "fiber_per_100g": 2.4, "magnesium_per_100g": 5, "potassium_per_100g": 107, "calcium_per_100g": 6, "iron_per_100g": 0.1, "zinc_per_100g": 0.04, "iodine_per_100g": 2, "selenium_per_100g": 0, "vitamin_c_per_100g": 4.6, "vitamin_a_per_100g": 3, "vitamin_e_per_100g": 0.2, "omega3_per_100g": 0.01},
    {"name": "банан", "calories_per_100g": 89, "protein_per_100g": 1.1, "fat_per_100g": 0.3, "carbs_per_100g": 23, "fiber_per_100g": 2.6, "magnesium_per_100g": 27, "potassium_per_100g": 358, "calcium_per_100g": 5, "iron_per_100g": 0.3, "zinc_per_100g": 0.2, "iodine_per_100g": 2, "selenium_per_100g": 1, "vitamin_c_per_100g": 8.7, "vitamin_a_per_100g": 3, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.03},
    {"name": "чечевица", "calories_per_100g": 116, "protein_per_100g": 9, "fat_per_100g": 0.4, "carbs_per_100g": 20, "fiber_per_100g": 7.9, "magnesium_per_100g": 36, "potassium_per_100g": 369, "calcium_per_100g": 19, "iron_per_100g": 3.3, "zinc_per_100g": 1.3, "iodine_per_100g": 0, "selenium_per_100g": 3, "vitamin_c_per_100g": 1.5, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.04},
    {"name": "фасоль", "calories_per_100g": 127, "protein_per_100g": 8.7, "fat_per_100g": 0.5, "carbs_per_100g": 23, "fiber_per_100g": 6.4, "magnesium_per_100g": 45, "potassium_per_100g": 405, "calcium_per_100g": 28, "iron_per_100g": 2.9, "zinc_per_100g": 1.0, "iodine_per_100g": 0, "selenium_per_100g": 1, "vitamin_c_per_100g": 1.2, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.05},
    {"name": "шпинат", "calories_per_100g": 23, "protein_per_100g": 2.9, "fat_per_100g": 0.4, "carbs_per_100g": 3.6, "fiber_per_100g": 2.2, "magnesium_per_100g": 79, "potassium_per_100g": 558, "calcium_per_100g": 99, "iron_per_100g": 2.7, "zinc_per_100g": 0.5, "iodine_per_100g": 12, "selenium_per_100g": 1, "vitamin_c_per_100g": 28, "vitamin_a_per_100g": 469, "vitamin_e_per_100g": 2.0, "omega3_per_100g": 0.14},
    {"name": "орехи", "calories_per_100g": 607, "protein_per_100g": 20, "fat_per_100g": 54, "carbs_per_100g": 20, "fiber_per_100g": 7, "magnesium_per_100g": 170, "potassium_per_100g": 600, "calcium_per_100g": 120, "iron_per_100g": 3.5, "zinc_per_100g": 3.0, "iodine_per_100g": 2, "selenium_per_100g": 5, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 1, "vitamin_e_per_100g": 8, "omega3_per_100g": 4.0},
    {"name": "оливковое масло", "calories_per_100g": 884, "protein_per_100g": 0, "fat_per_100g": 100, "carbs_per_100g": 0, "fiber_per_100g": 0, "magnesium_per_100g": 0, "potassium_per_100g": 1, "calcium_per_100g": 1, "iron_per_100g": 0.6, "zinc_per_100g": 0, "iodine_per_100g": 0, "selenium_per_100g": 0, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 14, "omega3_per_100g": 0.8},
]

SEED_FOODS.extend(
    [
        {"name": "утка", "calories_per_100g": 337, "protein_per_100g": 19, "fat_per_100g": 28, "carbs_per_100g": 0, "fiber_per_100g": 0, "magnesium_per_100g": 19, "potassium_per_100g": 204, "calcium_per_100g": 11, "iron_per_100g": 2.7, "zinc_per_100g": 1.9, "iodine_per_100g": 0, "selenium_per_100g": 14, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 50, "vitamin_e_per_100g": 0.7, "omega3_per_100g": 0.2},
        {"name": "картофель", "calories_per_100g": 87, "protein_per_100g": 1.9, "fat_per_100g": 0.1, "carbs_per_100g": 20, "fiber_per_100g": 1.8, "magnesium_per_100g": 22, "potassium_per_100g": 379, "calcium_per_100g": 5, "iron_per_100g": 0.3, "zinc_per_100g": 0.3, "iodine_per_100g": 5, "selenium_per_100g": 0.3, "vitamin_c_per_100g": 13, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.01, "omega3_per_100g": 0.01},
        {"name": "сметана", "calories_per_100g": 206, "protein_per_100g": 2.8, "fat_per_100g": 20, "carbs_per_100g": 3.2, "fiber_per_100g": 0, "magnesium_per_100g": 8, "potassium_per_100g": 95, "calcium_per_100g": 88, "iron_per_100g": 0.2, "zinc_per_100g": 0.2, "iodine_per_100g": 7, "selenium_per_100g": 3, "vitamin_c_per_100g": 0.3, "vitamin_a_per_100g": 160, "vitamin_e_per_100g": 0.6, "omega3_per_100g": 0.05},
        {"name": "песто", "calories_per_100g": 430, "protein_per_100g": 5, "fat_per_100g": 42, "carbs_per_100g": 8, "fiber_per_100g": 2, "magnesium_per_100g": 45, "potassium_per_100g": 180, "calcium_per_100g": 180, "iron_per_100g": 1.5, "zinc_per_100g": 1.0, "iodine_per_100g": 0, "selenium_per_100g": 2, "vitamin_c_per_100g": 3, "vitamin_a_per_100g": 120, "vitamin_e_per_100g": 8, "omega3_per_100g": 0.5},
        {"name": "виноградный сок", "calories_per_100g": 60, "protein_per_100g": 0.3, "fat_per_100g": 0.1, "carbs_per_100g": 15, "fiber_per_100g": 0.2, "magnesium_per_100g": 10, "potassium_per_100g": 104, "calcium_per_100g": 11, "iron_per_100g": 0.3, "zinc_per_100g": 0.1, "iodine_per_100g": 0, "selenium_per_100g": 0, "vitamin_c_per_100g": 0.1, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0},
    ]
)

SEED_FOODS.extend(
    [
        {"name": "рис", "calories_per_100g": 130, "protein_per_100g": 2.7, "fat_per_100g": 0.3, "carbs_per_100g": 28, "fiber_per_100g": 0.4, "magnesium_per_100g": 12, "potassium_per_100g": 35, "calcium_per_100g": 10, "iron_per_100g": 0.2, "zinc_per_100g": 0.5, "iodine_per_100g": 0, "selenium_per_100g": 7.5, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.0, "omega3_per_100g": 0.0},
        {"name": "ягоды", "calories_per_100g": 50, "protein_per_100g": 0.7, "fat_per_100g": 0.3, "carbs_per_100g": 12, "fiber_per_100g": 2.4, "magnesium_per_100g": 6, "potassium_per_100g": 77, "calcium_per_100g": 6, "iron_per_100g": 0.3, "zinc_per_100g": 0.2, "iodine_per_100g": 0, "selenium_per_100g": 0.1, "vitamin_c_per_100g": 10, "vitamin_a_per_100g": 3, "vitamin_e_per_100g": 0.6, "omega3_per_100g": 0.05},
        {"name": "сыр", "calories_per_100g": 350, "protein_per_100g": 24, "fat_per_100g": 27, "carbs_per_100g": 2, "fiber_per_100g": 0, "magnesium_per_100g": 28, "potassium_per_100g": 98, "calcium_per_100g": 700, "iron_per_100g": 0.5, "zinc_per_100g": 3.5, "iodine_per_100g": 20, "selenium_per_100g": 14, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 260, "vitamin_e_per_100g": 0.6, "omega3_per_100g": 0.1},
        {"name": "кефир", "calories_per_100g": 50, "protein_per_100g": 3, "fat_per_100g": 2.5, "carbs_per_100g": 4, "fiber_per_100g": 0, "magnesium_per_100g": 14, "potassium_per_100g": 146, "calcium_per_100g": 120, "iron_per_100g": 0.1, "zinc_per_100g": 0.4, "iodine_per_100g": 9, "selenium_per_100g": 2, "vitamin_c_per_100g": 0.7, "vitamin_a_per_100g": 22, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.02},
        {"name": "зелёный смузи", "calories_per_100g": 45, "protein_per_100g": 1.5, "fat_per_100g": 0.5, "carbs_per_100g": 9, "fiber_per_100g": 1.5, "magnesium_per_100g": 18, "potassium_per_100g": 180, "calcium_per_100g": 35, "iron_per_100g": 0.5, "zinc_per_100g": 0.2, "iodine_per_100g": 2, "selenium_per_100g": 0.5, "vitamin_c_per_100g": 15, "vitamin_a_per_100g": 80, "vitamin_e_per_100g": 0.5, "omega3_per_100g": 0.02},
    ]
)

SEED_FOODS.extend(
    [
        {"name": "\u043f\u0440\u043e\u0448\u0443\u0442\u0442\u043e", "calories_per_100g": 270, "protein_per_100g": 26, "fat_per_100g": 18, "carbs_per_100g": 0.5, "fiber_per_100g": 0, "magnesium_per_100g": 24, "potassium_per_100g": 450, "calcium_per_100g": 12, "iron_per_100g": 1.2, "zinc_per_100g": 2.3, "iodine_per_100g": 0, "selenium_per_100g": 22, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.3, "omega3_per_100g": 0.04},
        {"name": "\u043f\u043e\u0434\u0441\u043e\u043b\u043d\u0435\u0447\u043d\u043e\u0435 \u043c\u0430\u0441\u043b\u043e", "calories_per_100g": 899, "protein_per_100g": 0, "fat_per_100g": 99.9, "carbs_per_100g": 0, "fiber_per_100g": 0, "magnesium_per_100g": 0, "potassium_per_100g": 0, "calcium_per_100g": 0, "iron_per_100g": 0, "zinc_per_100g": 0, "iodine_per_100g": 0, "selenium_per_100g": 0, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 41, "omega3_per_100g": 0.2},
        {"name": "\u043c\u0430\u0442\u0447\u0430 \u043b\u0430\u0442\u0442\u0435", "calories_per_100g": 65, "protein_per_100g": 2.2, "fat_per_100g": 2.0, "carbs_per_100g": 9.5, "fiber_per_100g": 0.1, "magnesium_per_100g": 12, "potassium_per_100g": 80, "calcium_per_100g": 75, "iron_per_100g": 0.2, "zinc_per_100g": 0.3, "iodine_per_100g": 4, "selenium_per_100g": 1, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 25, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.02},
        {"name": "\u0441\u0430\u0445\u0430\u0440", "calories_per_100g": 399, "protein_per_100g": 0, "fat_per_100g": 0, "carbs_per_100g": 99.8, "fiber_per_100g": 0, "magnesium_per_100g": 0, "potassium_per_100g": 2, "calcium_per_100g": 1, "iron_per_100g": 0, "zinc_per_100g": 0, "iodine_per_100g": 0, "selenium_per_100g": 0, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0, "omega3_per_100g": 0},
        {"name": "\u043c\u043e\u043b\u043e\u043a\u043e", "calories_per_100g": 52, "protein_per_100g": 3.0, "fat_per_100g": 2.5, "carbs_per_100g": 4.8, "fiber_per_100g": 0, "magnesium_per_100g": 13, "potassium_per_100g": 146, "calcium_per_100g": 120, "iron_per_100g": 0.1, "zinc_per_100g": 0.4, "iodine_per_100g": 16, "selenium_per_100g": 2, "vitamin_c_per_100g": 1, "vitamin_a_per_100g": 28, "vitamin_e_per_100g": 0.1, "omega3_per_100g": 0.02},
        {"name": "\u0441\u0443\u0448\u043a\u0438", "calories_per_100g": 330, "protein_per_100g": 10, "fat_per_100g": 1.3, "carbs_per_100g": 70, "fiber_per_100g": 2.5, "magnesium_per_100g": 20, "potassium_per_100g": 110, "calcium_per_100g": 25, "iron_per_100g": 1.8, "zinc_per_100g": 0.7, "iodine_per_100g": 2, "selenium_per_100g": 10, "vitamin_c_per_100g": 0, "vitamin_a_per_100g": 0, "vitamin_e_per_100g": 0.3, "omega3_per_100g": 0.02},
    ]
)

SEED_FOODS.extend(TYPICAL_FOODS)


async def seed() -> None:
    async with async_session_maker() as session:
        created = 0
        for data in SEED_FOODS:
            result = await session.execute(select(Food).where(Food.name == data["name"]))
            food = result.scalar_one_or_none()
            if food:
                continue
            session.add(Food(**data, source="mvp_seed"))
            created += 1
        await session.commit()
    logger.info("Seed complete: %s foods created", created)


if __name__ == "__main__":
    asyncio.run(seed())
