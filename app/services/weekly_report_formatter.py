import html
from datetime import timedelta

from app.schemas import AllTimeReport, WeeklyReport, YearReport
from app.services.reports import (
    WEEKDAY_LABELS,
    WEEKLY_NUTRIENT_SECTIONS,
    _deviation_text,
    _plural_ru,
    _weekly_motivation,
    _weekly_score_value,
)
from app.text import fix_text, normalize_public_nutrition_terms


def format_weekly_report_html(report: WeeklyReport) -> str:
    score = report.score or _weekly_score_value(report)
    motivation = report.motivation or _weekly_motivation(score)
    period_label = fix_text(report.period_label or "Неделя")
    score_label = _period_score_label(period_label)

    sections = [
        f"📊 <b>{html.escape(period_label)} {report.start_date:%d.%m}-{report.end_date:%d.%m}</b>",
        _filled_days_block(report),
        _kbju_block(report),
        _weekly_factors_block(report),
        _weekly_micronutrients_block(report),
        _weekly_recommendations_block(report),
        f"⭐ <b>{html.escape(score_label)}: {score}/10</b>",
        f"💬 {html.escape(fix_text(motivation))}",
    ]
    return "\n\n".join(section.strip() for section in sections if section and section.strip())


def _filled_days_block(report: WeeklyReport) -> str:
    return "\n".join(
        (
            "🗓 <b>Заполненные дни</b>",
            f"{report.qualified_days}/{report.period_days} дней с хотя бы одной записью",
            _week_diet_grid(report).strip(),
            f"Лучшая серия записей: {report.best_streak_days} {_plural_ru(report.best_streak_days, 'день', 'дня', 'дней')} подряд",
        )
    )


def _kbju_block(report: WeeklyReport) -> str:
    period_days = max(1, int(report.period_days or len(report.diet_days) or 7))
    target_calories = report.calories_target / period_days
    avg_label = "Среднее за заполненный день" if 0 < report.qualified_days < report.period_days else "Среднее за день"
    lines = [
        "🍽 <b>КБЖУ</b>",
        f"{avg_label}:",
        f"Калории: {report.avg_calories:.0f} из {target_calories:.0f} ккал ({fix_text(_deviation_text(target_calories - report.avg_calories, 'ккал'))})",
        f"Белок: {report.avg_protein:.0f} из {report.protein_target:.0f} г ({fix_text(_deviation_text(report.protein_target - report.avg_protein, 'г'))})",
        f"Жиры: {report.avg_fat:.0f} из {report.fat_target:.0f} г ({fix_text(_deviation_text(report.fat_target - report.avg_fat, 'г'))})",
        f"Углеводы: {report.avg_carbs:.0f} из {report.carbs_target:.0f} г ({fix_text(_deviation_text(report.carbs_target - report.avg_carbs, 'г'))})",
        "",
        f"Всего записано: {report.calories_fact:.0f} ккал",
    ]
    if report.weight_delta_kg is None:
        lines.append("Вес: пока мало записей")
    else:
        sign = "+" if report.weight_delta_kg > 0 else ""
        lines.append(f"Динамика веса: {sign}{report.weight_delta_kg:.1f} кг")
    return "\n".join(lines)


def _nutrient_level(fact: float, target: float, mode: str) -> str:
    if target <= 0:
        return "ok"
    if mode == "max":
        if fact <= target:
            return "ok"
        if fact <= target * 1.2:
            return "mid"
        return "low"
    ratio = fact / target
    if ratio >= 0.9:
        return "ok"
    if ratio >= 0.6:
        return "mid"
    return "low"


def _nutrient_status(fact: float, target: float, unit: str, digits: int, mode: str) -> str:
    if mode == "max":
        if fact <= target:
            return "норма"
        return f"+{fact - target:.{digits}f} {unit}"
    if fact >= target:
        return "норма"
    return f"-{target - fact:.{digits}f} {unit}"


def _format_amount(value: float, digits: int) -> str:
    return f"{value:.0f}" if digits == 0 else f"{value:.{digits}f}"


def _period_score_label(period_label: str) -> str:
    lowered = period_label.lower()
    if "месяц" in lowered:
        return "Оценка месяца"
    if "год" in lowered:
        return "Оценка года"
    return "Оценка недели"


def _factor_icon(score: int) -> str:
    if score >= 8:
        return "✅"
    if score >= 5:
        return "🟡"
    return "🔴"


def _weekly_factors_block(report: WeeklyReport) -> str:
    factors = (
        ("Гликемическая нагрузка", report.glycemic_score, report.glycemic_comment),
        ("Воспалительный фактор", report.inflammation_score, report.inflammation_comment),
        ("Кислотно-щелочной баланс", report.acid_base_score, report.acid_base_comment),
    )
    if not any(score > 0 for _, score, _ in factors):
        return ""

    lines = ["⚖️ <b>Индексы качества</b>"]
    for label, score, comment in factors:
        if score <= 0:
            continue
        cleaned_comment = html.escape(normalize_public_nutrition_terms(comment).strip()) if comment else ""
        suffix = f". {cleaned_comment}" if cleaned_comment else ""
        lines.append(f"{_factor_icon(score)} {html.escape(label)}: {score}/10{suffix}")
    return "\n".join(lines)


def _weekly_micronutrients_block(report: WeeklyReport) -> str:
    period_days = max(1, int(report.period_days or 7))
    target_days = max(1, report.qualified_days or period_days)
    period_text = (
        f"{target_days} заполненных дней"
        if 0 < report.qualified_days < period_days
        else f"{period_days} дней"
    )
    counts = {"ok": 0, "mid": 0, "low": 0}
    for _, nutrients in WEEKLY_NUTRIENT_SECTIONS:
        for key, _, daily_target, _, _, mode in nutrients:
            target = daily_target * target_days
            level = _nutrient_level(report.micronutrients_7d.get(key, 0), target, mode)
            counts[level] += 1

    lines = [
        f"🔬 <b>Витамины и микроэлементы за {period_text}</b>",
        f"✅ закрыто: {counts['ok']} | 🟡 частично: {counts['mid']} | 🔴 проседает: {counts['low']}",
        "",
    ]
    icons = {"ok": "✅", "mid": "🟡", "low": "🔴"}
    for title, nutrients in WEEKLY_NUTRIENT_SECTIONS:
        lines.append(f"<b>{html.escape(fix_text(title).rstrip(':'))}</b>")
        for key, label, daily_target, unit, digits, mode in nutrients:
            target = daily_target * target_days
            fact = report.micronutrients_7d.get(key, 0)
            level = _nutrient_level(fact, target, mode)
            unit_text = fix_text(unit)
            status = _nutrient_status(fact, target, unit_text, digits, mode)
            lines.append(
                f"{icons[level]} {html.escape(fix_text(label))}: "
                f"{_format_amount(fact, digits)}/{_format_amount(target, digits)} {html.escape(unit_text)} "
                f"({html.escape(status)})"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_recommendation(item: str, index: int) -> str:
    text = _space_slashes(normalize_public_nutrition_terms(item).strip().lstrip("-").strip())
    product = text
    covers = ""
    reason = ""
    for marker in (" - закрывает:", " — закрывает:"):
        if marker in text:
            product, rest = text.split(marker, 1)
            if "; зачем:" in rest:
                covers, reason = rest.split("; зачем:", 1)
            else:
                covers = rest
            break
    if not covers:
        return f"{index}. {html.escape(text)}"

    lines = [f"{index}. <b>{html.escape(product.strip())}</b>"]
    lines.append(f"   Закрывает: {html.escape(covers.strip())}")
    if reason.strip():
        lines.append(f"   Зачем: {html.escape(reason.strip())}")
    return "\n".join(lines)


def _space_slashes(text: str) -> str:
    return " / ".join(part.strip() for part in text.split("/"))


def _weekly_recommendations_block(report: WeeklyReport) -> str:
    if not report.recommendations:
        return ""
    title = "Что добавить на следующий месяц" if "месяц" in (report.period_label or "").lower() else "Что добавить на следующую неделю"
    lines = [f"🥗 <b>{title}</b>"]
    lines.extend(_format_recommendation(item, index) for index, item in enumerate(report.recommendations, start=1))
    return "\n".join(lines)


def _week_diet_grid(report: WeeklyReport) -> str:
    if not report.diet_days:
        return ""
    if len(report.diet_days) <= 10:
        labels = [
            fix_text(WEEKDAY_LABELS[(report.start_date + timedelta(days=index)).weekday()])
            for index in range(len(report.diet_days))
        ]
        marks = ["🟩" if is_done else "⬜" for is_done in report.diet_days]
        return f"{' '.join(labels)}\n{' '.join(marks)}\nЗелёный день = была хотя бы одна запись\n"

    lines: list[str] = []
    for start in range(0, len(report.diet_days), 7):
        chunk = report.diet_days[start : start + 7]
        labels = [f"{(report.start_date + timedelta(days=start + index)).day:02d}" for index in range(len(chunk))]
        marks = ["🟩" if is_done else "⬜" for is_done in chunk]
        lines.append(" ".join(labels))
        lines.append(" ".join(marks))
    lines.append("Зелёный день = была хотя бы одна запись")
    return "\n".join(lines) + "\n"


def format_year_report_html(report: YearReport) -> str:
    score = max(0, min(10, int(report.score or 0)))
    lines = [
        f"📆 <b>Год {report.year}</b>",
        f"Период: {report.start_date:%d.%m.%Y}-{report.end_date:%d.%m.%Y}",
        "",
        "Цвета недель: 🟩 7-10 | 🟧 4-6 | 🟥 1-3 | ⬜ нет записей",
        "",
        "📊 <b>Месяцы и недели</b>",
    ]
    for month in report.months:
        week_marks = "".join(_year_week_mark(week.score, week.has_entries) for week in month.week_summaries)
        if month.has_entries:
            summary = f"{month.score}/10, дней: {month.qualified_days}, ср.: {month.avg_calories:.0f} ккал"
        else:
            summary = "нет записей"
        lines.append(f"{week_marks} <b>{html.escape(month.label)}</b>: {summary}")

    lines.extend(
        (
            "",
            f"⭐ <b>Оценка года: {score}/10</b>" if score else "⭐ <b>Оценка года: нет данных</b>",
            f"💬 {html.escape(_year_motivation(score))}",
        )
    )
    return "\n".join(lines)


def format_all_time_report_html(report: AllTimeReport) -> str:
    score = max(0, min(10, int(report.score or 0)))
    lines = [
        "🧭 <b>За все время</b>",
        f"Период: {report.start_date:%d.%m.%Y}-{report.end_date:%d.%m.%Y}",
        "",
        "📌 <b>Итог</b>",
        f"Заполненные дни: {report.qualified_days}",
        f"Записей еды: {report.total_entries}",
    ]
    if report.avg_calories > 0:
        lines.append(f"Средние калории: {report.avg_calories:.0f} ккал/день")
    if report.weight_delta_kg is not None:
        lines.append(f"Динамика веса: {_format_weight_delta(report.weight_delta_kg)}")

    lines.extend(
        [
            "",
            "📆 <b>Годы</b>",
            "Цвета месяцев: 🟩 7-10 | 🟧 4-6 | 🟥 1-3 | ⬜ нет записей",
        ]
    )
    if not report.years:
        lines.append("Пока нет записей еды.")
    for year in report.years:
        month_marks = "".join(_year_week_mark(month.score, month.has_entries) for month in year.months)
        if year.has_entries:
            summary = (
                f"{year.score}/10, дней: {year.qualified_days}, "
                f"записей: {year.total_entries}, ср.: {year.avg_calories:.0f} ккал"
            )
        else:
            summary = "нет записей"
        lines.append(f"{month_marks} <b>{year.year}</b>: {summary}")

    lines.extend(
        [
            "",
            f"⭐ <b>Оценка за все время: {score}/10</b>" if score else "⭐ <b>Оценка за все время: нет данных</b>",
            f"💬 {html.escape(_all_time_motivation(score))}",
        ]
    )
    return "\n".join(lines)


def _format_weight_delta(delta: float) -> str:
    if abs(delta) < 0.05:
        return "без изменений"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f} кг"


def _year_week_mark(score: int, has_entries: bool) -> str:
    if not has_entries:
        return "⬜"
    if score >= 7:
        return "🟩"
    if score >= 4:
        return "🟧"
    return "🟥"


def _year_motivation(score: int) -> str:
    if score >= 8:
        return "Сильная динамика: большинство недель уже держится в зеленой зоне."
    if score >= 6:
        return "Хорошая база: видно, какие недели подтянуть до зеленой зоны."
    if score >= 3:
        return "Главная цель сейчас — регулярность записей и несколько простых повторяемых приемов пищи."
    if score >= 1:
        return "Даже красные недели полезны: они показывают, где рацион проще всего улучшить."
    return "Начнем с серых недель: хотя бы одна запись в день уже даст понятную картину."


def _all_time_motivation(score: int) -> str:
    if score >= 8:
        return "Отличная долгосрочная база: привычка уже держится не на усилии, а на системе."
    if score >= 6:
        return "Хорошая динамика: видно, какие месяцы дают лучший результат и их можно повторять."
    if score >= 3:
        return "Главный ресурс сейчас — регулярность: чем больше заполненных дней, тем точнее подсказки."
    if score >= 1:
        return "Старт уже есть: даже редкие записи помогают увидеть повторяющиеся ошибки и удачные дни."
    return "Начни с простого: одна запись в день уже запустит полезную статистику."
