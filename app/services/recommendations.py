from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StandardMeal, User
from app.services.reports import build_daily_report


async def recommend_next_meal(session: AsyncSession, user: User) -> str:
    report = await build_daily_report(session, user)
    remaining_calories = user.calorie_target - report.calories_fact
    remaining_protein = user.protein_target - report.protein_fact
    remaining_fat = user.fat_target - report.fat_fact
    remaining_carbs = user.carb_target - report.carbs_fact

    result = await session.execute(select(StandardMeal).where(StandardMeal.user_id == user.id))
    meals = list(result.scalars().all())
    if meals and remaining_calories > 300:
        best = min(
            meals,
            key=lambda meal: abs(meal.total_calories - max(remaining_calories, 0))
            + abs(meal.total_protein - max(remaining_protein, 0)) * 8,
        )
        return (
            f"Совет: можно выбрать шаблон «{best.name}». "
            "Если хочется обычной еды: курица/рыба 120 г (1 ладонь) + овощи 200 г (1 большая миска), "
            "а крупу 100-150 г (1/2-3/4 стакана) добавь только если голодная."
        )

    if remaining_calories <= 150:
        return (
            "Совет: калорий почти не осталось. Лучше сделать лёгкий вариант: "
            "чай/вода, овощи 150 г (1 миска) или творог 60-80 г (2-3 ст. л.), если голодно."
        )

    if remaining_protein > 45:
        return (
            "Совет: добери белок. Подойдёт рыба/курица 120-150 г (1 ладонь), "
            "или 2 яйца, или творог 150 г (1 небольшая миска). Добавь салат 150-200 г (1 большая миска)."
        )

    if remaining_protein > 25:
        return (
            "Совет: нужен небольшой белковый приём. Подойдут 2 яйца, "
            "творог 100 г (1/2 миски) или рыба/курица 100-120 г (1 ладонь) плюс овощи 150 г (1 миска)."
        )

    if remaining_fat < 5:
        return (
            "Совет: жиры почти закрыты. Лучше без масла и орехов: "
            "овощи 200 г (1 большая миска), нежирный творог 150 г (1 небольшая миска), рыба/курица 120 г (1 ладонь)."
        )

    if remaining_carbs < 20:
        return (
            "Совет: углеводы почти закрыты. Лучше белок с овощами: "
            "рыба/курица 120 г (1 ладонь) или 2 яйца и салат 150-200 г (1 большая миска)."
        )

    return (
        "Совет: нормальный вариант на следующий приём — белок 120 г (1 ладонь), "
        "овощи 200 г (1 большая миска) и крупа 100-150 г (3-5 ст. л. или 1/2-3/4 стакана), если нужен более сытный приём."
    )
