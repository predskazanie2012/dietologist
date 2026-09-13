import calendar
import html
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityLog, MealLog, User, WeightLog
from app.schemas import (
    AllTimeReport,
    AllTimeYearSummary,
    DailyReport,
    MICRONUTRIENT_KEYS,
    WeeklyReport,
    YearMonthSummary,
    YearReport,
    YearWeekSummary,
)
from app.services.openai_weekly_nutrients import analyze_weekly_nutrition
from app.text import fix_text


DAILY_FIBER_TARGET = 25
WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
WEEKLY_NUTRIENT_SECTIONS = (
    (
        "Витамины и холин:",
        (
            ("vitamin_a", "Витамин A", 900, "мкг RAE", 0, "min"),
            ("vitamin_c", "Витамин C", 90, "мг", 0, "min"),
            ("vitamin_d", "Витамин D", 20, "мкг", 0, "min"),
            ("vitamin_e", "Витамин E", 15, "мг", 1, "min"),
            ("vitamin_k", "Витамин K", 120, "мкг", 0, "min"),
            ("thiamin", "Витамин B1", 1.2, "мг", 1, "min"),
            ("riboflavin", "Витамин B2", 1.3, "мг", 1, "min"),
            ("niacin", "Витамин B3", 16, "мг NE", 0, "min"),
            ("pantothenic_acid", "Витамин B5", 5, "мг", 1, "min"),
            ("vitamin_b6", "Витамин B6", 1.7, "мг", 1, "min"),
            ("biotin", "Биотин B7", 30, "мкг", 0, "min"),
            ("folate", "Фолат B9", 400, "мкг DFE", 0, "min"),
            ("vitamin_b12", "Витамин B12", 2.4, "мкг", 1, "min"),
            ("choline", "Холин", 550, "мг", 0, "min"),
        ),
    ),
    (
        "Минералы и электролиты:",
        (
            ("calcium", "Кальций", 1300, "мг", 0, "min"),
            ("chloride", "Хлорид", 2300, "мг", 0, "min"),
            ("chromium", "Хром", 35, "мкг", 0, "min"),
            ("copper", "Медь", 0.9, "мг", 1, "min"),
            ("fluoride", "Фтор", 3, "мг", 1, "min"),
            ("iodine", "Йод", 150, "мкг", 0, "min"),
            ("iron", "Железо", 18, "мг", 1, "min"),
            ("magnesium", "Магний", 420, "мг", 0, "min"),
            ("manganese", "Марганец", 2.3, "мг", 1, "min"),
            ("molybdenum", "Молибден", 45, "мкг", 0, "min"),
            ("phosphorus", "Фосфор", 1250, "мг", 0, "min"),
            ("potassium", "Калий", 4700, "мг", 0, "min"),
            ("selenium", "Селен", 55, "мкг", 0, "min"),
            ("sodium", "Натрий", 2300, "мг", 0, "max"),
            ("zinc", "Цинк", 11, "мг", 1, "min"),
        ),
    ),
    (
        "Дополнительно:",
        (
            ("omega3", "Омега-3", 1.1, "г", 1, "min"),
        ),
    ),
)


async def _logs_between(session: AsyncSession, user: User, start: datetime, end: datetime) -> list[MealLog]:
    result = await session.execute(
        select(MealLog)
        .where(MealLog.user_id == user.id, MealLog.datetime >= start, MealLog.datetime < end)
        .order_by(MealLog.datetime)
    )
    return list(result.scalars().all())


def _daily_status(calories: float, target: float) -> str:
    if calories > target:
        return "выше дневной нормы"
    if target > 0 and calories >= target * 0.95:
        return "в пределах дневной нормы"
    return "ниже дневной нормы"


def _day_goal_met(meal_count: int, calories: float, target: float) -> bool:
    return meal_count > 0


async def _day_food_metrics(session: AsyncSession, user: User, report_date: date) -> tuple[int, float]:
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(report_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    logs = await _logs_between(session, user, start, end)
    return len(logs), sum(log.calories for log in logs)


async def _current_streak_days(
    session: AsyncSession,
    user: User,
    report_date: date,
    today_goal_met: bool,
    today_calories: float,
    max_days: int = 365,
) -> int:
    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    day = report_date
    streak = 0

    if not today_goal_met:
        if report_date == today and today_calories <= user.calorie_target:
            day = report_date - timedelta(days=1)
        else:
            return 0

    for _ in range(max_days):
        meal_count, calories = await _day_food_metrics(session, user, day)
        if not _day_goal_met(meal_count, calories, user.calorie_target):
            break
        streak += 1
        day -= timedelta(days=1)
    return streak


async def build_daily_report(session: AsyncSession, user: User, report_date: date | None = None) -> DailyReport:
    tz = ZoneInfo(user.timezone)
    report_date = report_date or datetime.now(tz).date()
    start = datetime.combine(report_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    logs = await _logs_between(session, user, start, end)
    meal_count = len(logs)

    calories = sum(log.calories for log in logs)
    protein = sum(log.protein for log in logs)
    fat = sum(log.fat for log in logs)
    carbs = sum(log.carbs for log in logs)
    fiber = sum(log.fiber for log in logs)
    activity_result = await session.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id, ActivityLog.date == report_date)
    )
    activity_logs = list(activity_result.scalars().all())
    steps = max((log.steps for log in activity_logs), default=0)
    active_calories = max((log.active_calories for log in activity_logs), default=0)
    total_burned_calories = max((log.total_calories for log in activity_logs), default=0)
    sleep_minutes = max((log.sleep_minutes for log in activity_logs), default=0)
    heart_rates = [log.avg_heart_rate for log in activity_logs if log.avg_heart_rate]
    avg_heart_rate = sum(heart_rates) / len(heart_rates) if heart_rates else None
    estimated_balance = calories - total_burned_calories if total_burned_calories > 0 else None
    status = _daily_status(calories, user.calorie_target)
    day_goal_met = _day_goal_met(meal_count, calories, user.calorie_target)
    streak_days = await _current_streak_days(session, user, report_date, day_goal_met, calories)

    good = "День записан." if logs else "День пока без записей."
    if protein >= user.protein_target * 0.9:
        good = "Белок близко к дневной норме."

    improve = "Добавь следующий приём пищи текстом или шаблоном."
    if protein < user.protein_target * 0.75:
        improve = "Белка пока мало: подойдут рыба 120 г (1 ладонь), курица 120 г (1 ладонь), 2 яйца или творог 150 г (1 небольшая миска)."
    elif fiber < 20:
        improve = "Клетчатку можно добрать овощами 200 г (1 большая миска), бобовыми 150 г (3/4 стакана) или яблоком 150 г (1 среднее)."

    return DailyReport(
        date=report_date,
        calories_fact=calories,
        calories_target=user.calorie_target,
        protein_fact=protein,
        protein_target=user.protein_target,
        fat_fact=fat,
        fat_target=user.fat_target,
        carbs_fact=carbs,
        carbs_target=user.carb_target,
        fiber_fact=fiber,
        meal_count=meal_count,
        day_goal_met=day_goal_met,
        streak_days=streak_days,
        steps=steps,
        active_calories=active_calories,
        total_burned_calories=total_burned_calories,
        estimated_balance_calories=estimated_balance,
        sleep_minutes=sleep_minutes,
        avg_heart_rate=avg_heart_rate,
        status=status,
        good=good,
        improve=improve,
    )


def format_daily_report(report: DailyReport) -> str:
    return f"Итог дня ({report.date:%d.%m.%Y})\n\n{format_daily_summary(report)}"


def format_daily_summary(report: DailyReport) -> str:
    diff = report.calories_target - report.calories_fact
    calorie_delta = (
        f"До дневной нормы ещё {diff:.0f} ккал"
        if diff > 0
        else f"Выше дневной нормы на {abs(diff):.0f} ккал"
        if diff < 0
        else "Дневная норма по калориям закрыта"
    )
    marker = "🟢" if report.meal_count > 0 else "⚪"
    title = "День записан" if report.meal_count > 0 else "День пока без записей"
    summary = (
        f"{marker} {title}\n\n"
        f"Записей сегодня: {report.meal_count}\n\n"
        f"Калории: {report.calories_fact:.0f} из {report.calories_target:.0f}\n"
        f"{calorie_delta}\n\n"
        f"Белок: {report.protein_fact:.0f} из {report.protein_target:.0f} г\n"
        f"Жиры: {report.fat_fact:.0f} из {report.fat_target:.0f} г\n"
        f"Углеводы: {report.carbs_fact:.0f} из {report.carbs_target:.0f} г\n"
        f"Клетчатка: {report.fiber_fact:.0f} из {DAILY_FIBER_TARGET:.0f} г\n\n"
        f"Баланс: {_daily_balance_text(report)}"
    )
    activity = _activity_block(report).strip()
    if activity:
        summary += f"\n\n{activity}"
    return summary


def _daily_balance_text(report: DailyReport) -> str:
    if report.calories_target <= 0:
        return "дневная норма не задана"
    diff = report.calories_fact - report.calories_target
    if abs(diff) <= report.calories_target * 0.05:
        return "в пределах дневной нормы"
    if diff > 0:
        return "выше дневной нормы"
    return "ниже дневной нормы"


def _plural_ru(value: int, one: str, few: str, many: str) -> str:
    value_abs = abs(value)
    if value_abs % 10 == 1 and value_abs % 100 != 11:
        return one
    if 2 <= value_abs % 10 <= 4 and not 12 <= value_abs % 100 <= 14:
        return few
    return many


def _activity_block(report: DailyReport) -> str:
    if not any([report.steps, report.active_calories, report.total_burned_calories, report.sleep_minutes, report.avg_heart_rate]):
        return ""
    lines = ["Активность:"]
    if report.steps:
        lines.append(f"Шаги: {report.steps}")
    if report.active_calories:
        lines.append(f"Активные калории: {report.active_calories:.0f} ккал")
    if report.total_burned_calories:
        lines.append(f"Всего потрачено: {report.total_burned_calories:.0f} ккал")
    if report.estimated_balance_calories is not None:
        lines.append(f"Оценочный баланс: {report.estimated_balance_calories:+.0f} ккал")
    if report.sleep_minutes:
        lines.append(f"Сон: {report.sleep_minutes / 60:.1f} ч")
    if report.avg_heart_rate:
        lines.append(f"Средний пульс: {report.avg_heart_rate:.0f}")
    return "\n".join(lines) + "\n\n"


def _deviation_text(target_minus_fact: float, unit: str, digits: int = 0) -> str:
    if target_minus_fact > 0:
        return f"недобор {target_minus_fact:.{digits}f} {unit}"
    if target_minus_fact < 0:
        return f"перебор {abs(target_minus_fact):.{digits}f} {unit}"
    return "в норме"


def _range_score(fact: float, target: float, low_ratio: float = 0.85, high_ratio: float = 1.1) -> float:
    if target <= 0:
        return 1.0
    ratio = fact / target
    if low_ratio <= ratio <= high_ratio:
        return 1.0
    if ratio < low_ratio:
        return max(0.0, ratio / low_ratio)
    return max(0.0, 1 - ((ratio - high_ratio) / high_ratio))


def _min_score(fact: float, target: float) -> float:
    if target <= 0:
        return 1.0
    ratio = fact / target
    if ratio <= 1:
        return max(0.0, ratio)
    return max(0.75, 1 - ((ratio - 1) * 0.15))


def _nutrient_score(fact: float, target: float, mode: str) -> float:
    if target <= 0:
        return 1.0
    if mode == "max":
        return 1.0 if fact <= target else max(0.0, target / fact)
    return min(max(fact / target, 0.0), 1.0)


def _count_food_mentions(text: str, words: tuple[str, ...]) -> int:
    return sum(text.count(word) for word in words)


def _weekly_food_text(logs: list[MealLog]) -> str:
    parts: list[str] = []
    for log in logs:
        for value in (log.raw_user_input, log.notes, log.meal_type):
            if value:
                parts.append(fix_text(str(value)))
    return " ".join(parts).lower()


def _score_from_hits(base: float, good_hits: int, bad_hits: int, good_weight: float = 0.55, bad_weight: float = 0.7) -> int:
    score = base + min(good_hits, 7) * good_weight - min(bad_hits, 7) * bad_weight
    return max(1, min(10, int(round(score))))


def _fallback_weekly_factor_scores(logs: list[MealLog], avg_carbs: float, avg_fiber: float) -> dict[str, object]:
    text = _weekly_food_text(logs)

    glycemic_good = _count_food_mentions(
        text,
        (
            "греч",
            "перлов",
            "овсян",
            "чечев",
            "фасол",
            "нут",
            "боб",
            "овощ",
            "салат",
            "ягод",
            "цельнозерн",
        ),
    )
    glycemic_bad = _count_food_mentions(
        text,
        (
            "сахар",
            "сок",
            "слад",
            "булоч",
            "печень",
            "конфет",
            "десерт",
            "белый хлеб",
            "тостовый хлеб",
            "макдонал",
        ),
    )
    glycemic_base = 6.0
    if avg_fiber >= 25:
        glycemic_base += 1.5
    elif avg_fiber >= 15:
        glycemic_base += 0.5
    elif avg_fiber < 10:
        glycemic_base -= 1.5
    if avg_carbs > 230:
        glycemic_base -= 1
    glycemic_score = _score_from_hits(glycemic_base, glycemic_good, glycemic_bad)

    inflammation_good = _count_food_mentions(
        text,
        (
            "лосос",
            "семг",
            "сёмг",
            "скумбр",
            "сардин",
            "рыб",
            "овощ",
            "зелень",
            "ягод",
            "череш",
            "боб",
            "чечев",
            "фасол",
            "орех",
            "оливков",
            "авокад",
        ),
    )
    inflammation_bad = _count_food_mentions(
        text,
        (
            "сахар",
            "слад",
            "фастфуд",
            "макдонал",
            "жарен",
            "колбас",
            "сосиск",
            "бекон",
            "майонез",
            "чипс",
            "процес",
        ),
    )
    inflammation_score = _score_from_hits(6.0, inflammation_good, inflammation_bad)

    acid_good = _count_food_mentions(
        text,
        (
            "овощ",
            "зелень",
            "салат",
            "помид",
            "огур",
            "фрукт",
            "ягод",
            "череш",
            "абрикос",
            "чечев",
            "фасол",
            "нут",
            "картоф",
            "авокад",
        ),
    )
    acid_bad = _count_food_mentions(
        text,
        (
            "мяс",
            "свинин",
            "говяд",
            "куриц",
            "индейк",
            "сыр",
            "творог",
            "яйц",
            "рыб",
            "хлеб",
            "круп",
            "рис",
            "макарон",
        ),
    )
    acid_score = _score_from_hits(6.0, acid_good, acid_bad, 0.5, 0.35)

    def comment(score: int, good: str, mid: str, low: str) -> str:
        if score >= 8:
            return good
        if score >= 5:
            return mid
        return low

    return {
        "glycemic_score": glycemic_score,
        "glycemic_comment": comment(
            glycemic_score,
            "Углеводы выглядят достаточно ровно: есть клетчатка и цельные продукты.",
            "Средне: стоит чаще выбирать крупы, бобовые, ягоды и меньше соков/сладкого.",
            "Высокая нагрузка: много быстрых углеводов или мало клетчатки.",
        ),
        "inflammation_score": inflammation_score,
        "inflammation_comment": comment(
            inflammation_score,
            "Профиль ближе к противовоспалительному: есть рыба, овощи, ягоды или орехи.",
            "Средне: можно усилить рыбу, овощи, ягоды, бобовые и орехи.",
            "Провоспалительный перекос: стоит уменьшить сладкое, фастфуд и переработанное мясо.",
        ),
        "acid_base_score": acid_score,
        "acid_base_comment": comment(
            acid_score,
            "Баланс поддержан овощами, фруктами, зеленью или бобовыми.",
            "Средне: к белку и крупам стоит чаще добавлять овощи/зелень.",
            "Кислотная нагрузка высокая: мало овощей и много белковых/зерновых продуктов.",
        ),
    }


def _weekly_score_value(report: WeeklyReport) -> int:
    if not any(report.diet_days):
        return 1
    period_days = max(1, int(report.period_days or len(report.diet_days) or 7))
    recorded_days = max(1, sum(1 for day in report.diet_days if day))

    macro_score = sum(
        (
            _range_score(report.avg_calories, report.calories_target / period_days, 0.8, 1.1),
            _min_score(report.avg_protein, report.protein_target),
            _range_score(report.avg_fat, report.fat_target, 0.75, 1.15),
            _range_score(report.avg_carbs, report.carbs_target, 0.75, 1.15),
        )
    ) / 4

    nutrient_scores: list[float] = []
    for _, nutrients in WEEKLY_NUTRIENT_SECTIONS:
        for key, _, daily_target, _, _, mode in nutrients:
            target = daily_target * recorded_days
            fact = report.micronutrients_7d.get(key, 0)
            nutrient_scores.append(_nutrient_score(fact, target, mode))
    micro_score = sum(nutrient_scores) / len(nutrient_scores) if nutrient_scores else 0
    record_score = recorded_days / period_days
    factor_values = [
        value / 10
        for value in (report.glycemic_score, report.inflammation_score, report.acid_base_score)
        if value > 0
    ]
    factor_score = sum(factor_values) / len(factor_values) if factor_values else (macro_score + micro_score) / 2

    score = int(10 * ((macro_score * 0.28) + (micro_score * 0.32) + (record_score * 0.20) + (factor_score * 0.20)))
    return max(1, min(10, score))


def _weekly_motivation(score: int) -> str:
    if score >= 9:
        return "Отличная неделя: рацион уже выглядит сильным, дальше просто держим ритм и разнообразие."
    if score >= 7:
        return "Хорошая база: осталось точечно добрать несколько продуктов, и неделя станет заметно ровнее."
    if score >= 5:
        return "Нормальный старт: дневник уже показывает, что именно добрать на следующей неделе."
    if score >= 3:
        return "Есть от чего оттолкнуться: добавим регулярность, белок и продукты под дефициты без резких ограничений."
    if score >= 1:
        return "Начинаем спокойно: даже одна запись в день уже помогает видеть картину и двигаться дальше."
    return "Пока мало данных: начни с одной записи еды в день, и отчет станет полезнее."


async def build_period_report(
    session: AsyncSession,
    user: User,
    start_date: date,
    end_date: date,
    period_label: str,
    use_ai: bool = True,
) -> WeeklyReport:
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    logs = await _logs_between(session, user, start, end)
    logs_by_date: dict[date, list[MealLog]] = {}
    for log in logs:
        logs_by_date.setdefault(log.datetime.date(), []).append(log)

    micros = {key: 0.0 for key in MICRONUTRIENT_KEYS}
    for log in logs:
        for key in micros:
            micros[key] += float((log.micronutrients_json or {}).get(key, 0) or 0)

    result = await session.execute(
        select(WeightLog)
        .where(WeightLog.user_id == user.id, WeightLog.date >= start_date, WeightLog.date <= end_date)
        .order_by(WeightLog.date)
    )
    weights = list(result.scalars().all())
    weight_delta = None
    if len(weights) >= 2:
        weight_delta = weights[-1].weight_kg - weights[0].weight_kg

    days = max(1, (end_date - start_date).days + 1)
    qualified_days = 0
    best_streak = 0
    current_streak = 0
    diet_days = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        day_logs = logs_by_date.get(day, [])
        day_has_entry = bool(day_logs)
        diet_days.append(day_has_entry)
        if day_has_entry:
            qualified_days += 1
            current_streak += 1
            best_streak = max(best_streak, current_streak)
        else:
            current_streak = 0

    calories_fact = sum(log.calories for log in logs)
    calories_target = user.calorie_target * days
    protein_fact = sum(log.protein for log in logs)
    fat_fact = sum(log.fat for log in logs)
    carbs_fact = sum(log.carbs for log in logs)
    fiber_fact = sum(log.fiber for log in logs)
    nutrition_days = max(1, qualified_days or days)
    avg_calories = calories_fact / nutrition_days
    avg_protein = protein_fact / nutrition_days
    avg_fat = fat_fact / nutrition_days
    avg_carbs = carbs_fact / nutrition_days
    avg_fiber = fiber_fact / nutrition_days
    recommendations: list[str] = []
    factor_scores = _fallback_weekly_factor_scores(logs, avg_carbs, avg_fiber)
    nutrition_context = (
        "Цели и факт КБЖУ для рекомендаций:\n"
        f"- заполнено дней: {qualified_days}/{days};\n"
        f"- цель: {user.calorie_target:.0f} ккал/день, "
        f"белок {user.protein_target:.0f} г/день, жиры {user.fat_target:.0f} г/день, "
        f"углеводы {user.carb_target:.0f} г/день;\n"
        f"- факт в среднем по заполненным дням: {avg_calories:.0f} ккал/день, "
        f"белок {avg_protein:.0f} г/день, жиры {avg_fat:.0f} г/день, "
        f"углеводы {avg_carbs:.0f} г/день."
    )
    weekly_analysis = await analyze_weekly_nutrition(logs, nutrition_context, period_days=nutrition_days) if use_ai else None
    if weekly_analysis is not None:
        micros, recommendations, ai_factor_scores = weekly_analysis
        for key, value in ai_factor_scores.items():
            if key.endswith("_score") and int(value or 0) > 0:
                factor_scores[key] = int(value)
            elif key.endswith("_comment") and str(value or "").strip():
                factor_scores[key] = str(value).strip()

    report = WeeklyReport(
        period_label=period_label,
        period_days=days,
        start_date=start_date,
        end_date=end_date,
        calories_fact=calories_fact,
        calories_target=calories_target,
        avg_calories=avg_calories,
        avg_protein=avg_protein,
        avg_fat=avg_fat,
        avg_carbs=avg_carbs,
        protein_target=user.protein_target,
        fat_target=user.fat_target,
        carbs_target=user.carb_target,
        weight_delta_kg=weight_delta,
        qualified_days=qualified_days,
        best_streak_days=best_streak,
        diet_days=diet_days,
        micronutrients_7d=micros,
        recommendations=recommendations,
        glycemic_score=int(factor_scores.get("glycemic_score", 0) or 0),
        glycemic_comment=str(factor_scores.get("glycemic_comment", "") or ""),
        inflammation_score=int(factor_scores.get("inflammation_score", 0) or 0),
        inflammation_comment=str(factor_scores.get("inflammation_comment", "") or ""),
        acid_base_score=int(factor_scores.get("acid_base_score", 0) or 0),
        acid_base_comment=str(factor_scores.get("acid_base_comment", "") or ""),
    )
    report.score = _weekly_score_value(report)
    report.motivation = _weekly_motivation(report.score)
    return report


async def build_weekly_report(session: AsyncSession, user: User, end_date: date | None = None) -> WeeklyReport:
    tz = ZoneInfo(user.timezone)
    end_date = end_date or datetime.now(tz).date()
    start_date = end_date - timedelta(days=6)
    return await build_period_report(session, user, start_date, end_date, "Неделя")


async def build_monthly_report(session: AsyncSession, user: User, end_date: date | None = None) -> WeeklyReport:
    tz = ZoneInfo(user.timezone)
    end_date = end_date or datetime.now(tz).date()
    start_date = end_date - timedelta(days=29)
    return await build_period_report(session, user, start_date, end_date, "Месяц")


MONTH_LABELS = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


def _month_week_ranges(month_start: date, month_end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    start = month_start
    while start <= month_end:
        end = min(month_end, start + timedelta(days=6))
        ranges.append((start, end))
        start = end + timedelta(days=1)
    return ranges


async def build_year_report(session: AsyncSession, user: User, year: int | None = None) -> YearReport:
    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    year = year or today.year
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    report_end = min(today, year_end) if year == today.year else year_end
    months: list[YearMonthSummary] = []

    for month in range(1, 13):
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        week_summaries: list[YearWeekSummary] = []

        if month_start <= report_end:
            active_month_end = min(month_end, report_end)
            for week_start, week_end in _month_week_ranges(month_start, month_end):
                if week_start > report_end:
                    week_summaries.append(YearWeekSummary(start_date=week_start, end_date=week_end))
                    continue
                period_end = min(week_end, report_end)
                period = await build_period_report(
                    session,
                    user,
                    week_start,
                    period_end,
                    "Неделя",
                    use_ai=False,
                )
                has_entries = any(period.diet_days)
                week_summaries.append(
                    YearWeekSummary(
                        start_date=week_start,
                        end_date=period_end,
                        score=period.score if has_entries else 0,
                        has_entries=has_entries,
                        qualified_days=period.qualified_days,
                        avg_calories=period.avg_calories if has_entries else 0,
                    )
                )
        else:
            active_month_end = month_end
            for week_start, week_end in _month_week_ranges(month_start, month_end):
                week_summaries.append(YearWeekSummary(start_date=week_start, end_date=week_end))

        scored_weeks = [week for week in week_summaries if week.has_entries]
        month_score = round(sum(week.score for week in scored_weeks) / len(scored_weeks)) if scored_weeks else 0
        qualified_days = sum(week.qualified_days for week in week_summaries)
        active_weeks = [week for week in week_summaries if week.has_entries and week.avg_calories > 0]
        avg_calories = (
            sum(week.avg_calories for week in active_weeks) / len(active_weeks)
            if active_weeks
            else 0
        )
        months.append(
            YearMonthSummary(
                month=month,
                label=MONTH_LABELS[month - 1],
                start_date=month_start,
                end_date=active_month_end,
                week_summaries=week_summaries,
                score=month_score,
                has_entries=bool(scored_weeks),
                qualified_days=qualified_days,
                avg_calories=avg_calories,
            )
        )

    scored_months = [month for month in months if month.has_entries]
    score = round(sum(month.score for month in scored_months) / len(scored_months)) if scored_months else 0
    return YearReport(
        year=year,
        start_date=year_start,
        end_date=report_end,
        months=months,
        score=score,
    )


async def build_all_time_report(session: AsyncSession, user: User) -> AllTimeReport:
    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    result = await session.execute(
        select(MealLog)
        .where(MealLog.user_id == user.id)
        .order_by(MealLog.datetime)
    )
    logs = list(result.scalars().all())

    weight_result = await session.execute(
        select(WeightLog)
        .where(WeightLog.user_id == user.id)
        .order_by(WeightLog.date)
    )
    weights = list(weight_result.scalars().all())
    weight_delta = None
    if len(weights) >= 2:
        weight_delta = weights[-1].weight_kg - weights[0].weight_kg

    if not logs:
        return AllTimeReport(
            start_date=today,
            end_date=today,
            weight_delta_kg=weight_delta,
        )

    def log_date(log: MealLog) -> date:
        if log.datetime.tzinfo is not None:
            return log.datetime.astimezone(tz).date()
        return log.datetime.date()

    first_date = min(log_date(log) for log in logs)
    logs_by_year: dict[int, list[MealLog]] = {}
    days_by_year: dict[int, set[date]] = {}
    for log in logs:
        day = log_date(log)
        logs_by_year.setdefault(day.year, []).append(log)
        days_by_year.setdefault(day.year, set()).add(day)

    year_summaries: list[AllTimeYearSummary] = []
    for year in range(first_date.year, today.year + 1):
        year_report = await build_year_report(session, user, year)
        year_logs = logs_by_year.get(year, [])
        year_days = days_by_year.get(year, set())
        year_qualified_days = len(year_days)
        year_avg_calories = (
            sum(log.calories for log in year_logs) / year_qualified_days
            if year_qualified_days
            else 0
        )
        year_summaries.append(
            AllTimeYearSummary(
                year=year,
                start_date=year_report.start_date,
                end_date=year_report.end_date,
                months=year_report.months,
                score=year_report.score,
                has_entries=bool(year_logs),
                qualified_days=year_qualified_days,
                total_entries=len(year_logs),
                avg_calories=year_avg_calories,
            )
        )

    scored_years = [item for item in year_summaries if item.has_entries and item.score > 0]
    total_qualified_days = sum(item.qualified_days for item in year_summaries)
    total_entries = len(logs)
    avg_calories = (
        sum(log.calories for log in logs) / total_qualified_days
        if total_qualified_days
        else 0
    )
    if scored_years and total_qualified_days:
        score = round(
            sum(item.score * max(1, item.qualified_days) for item in scored_years)
            / sum(max(1, item.qualified_days) for item in scored_years)
        )
    else:
        score = 0

    return AllTimeReport(
        start_date=first_date,
        end_date=today,
        years=year_summaries,
        score=score,
        qualified_days=total_qualified_days,
        total_entries=total_entries,
        avg_calories=avg_calories,
        weight_delta_kg=weight_delta,
    )


def format_weekly_report(report: WeeklyReport) -> str:
    weight_line = "Вес: пока мало записей"
    if report.weight_delta_kg is not None:
        sign = "+" if report.weight_delta_kg > 0 else ""
        weight_line = f"Динамика веса: {sign}{report.weight_delta_kg:.1f} кг"

    return (
        f"Неделя {report.start_date:%d.%m}-{report.end_date:%d.%m}:\n"
        f"Калории за неделю: {report.calories_fact:.0f}/{report.calories_target:.0f} ({_deviation_text(report.calories_target - report.calories_fact, 'ккал')})\n"
        f"Средние калории: {report.avg_calories:.0f} ккал\n"
        "БЖУ в среднем за день:\n"
        f"Белок: {report.avg_protein:.0f}/{report.protein_target:.0f} г ({_deviation_text(report.protein_target - report.avg_protein, 'г')})\n"
        f"Жиры: {report.avg_fat:.0f}/{report.fat_target:.0f} г ({_deviation_text(report.fat_target - report.avg_fat, 'г')})\n"
        f"Углеводы: {report.avg_carbs:.0f}/{report.carbs_target:.0f} г ({_deviation_text(report.carbs_target - report.avg_carbs, 'г')})\n"
        f"{weight_line}\n"
        f"Диета за неделю: {report.qualified_days}/7\n"
        f"{_week_diet_grid(report)}"
        f"Лучшая серия: {report.best_streak_days} {_plural_ru(report.best_streak_days, 'день', 'дня', 'дней')} подряд\n"
        f"{_weekly_micronutrients_block(report)}"
        f"{_weekly_recommendations_block(report)}"
    )


def _weekly_micronutrients_block(report: WeeklyReport) -> str:
    lines = ["Витамины и микроэлементы за 7 дней (оценочно):"]
    for title, nutrients in WEEKLY_NUTRIENT_SECTIONS:
        lines.append(title)
        for key, label, daily_target, unit, digits, mode in nutrients:
            target = daily_target * 7
            fact = report.micronutrients_7d.get(key, 0)
            target_text = f"{target:.0f}" if float(target).is_integer() else f"{target:.{digits}f}"
            if mode == "max":
                status = "в пределах лимита" if fact <= target else f"перебор {fact - target:.{digits}f} {unit}"
            else:
                status = _deviation_text(target - fact, unit, digits)
            lines.append(f"{label}: {fact:.{digits}f}/{target_text} {unit} ({status})")
    return "\n".join(lines)


def _weekly_recommendations_block(report: WeeklyReport) -> str:
    if not report.recommendations:
        return ""
    lines = ["", "Что добавить на следующую неделю:"]
    lines.extend(f"- {fix_text(item)}" for item in report.recommendations)
    return "\n".join(lines)


def _week_diet_grid(report: WeeklyReport) -> str:
    if not report.diet_days:
        return ""
    labels = [
        WEEKDAY_LABELS[(report.start_date + timedelta(days=index)).weekday()]
        for index in range(len(report.diet_days))
    ]
    marks = ["🟩" if is_done else "⬜" for is_done in report.diet_days]
    return f"{' '.join(labels)}\n{' '.join(marks)}\n"

