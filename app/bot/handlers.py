import asyncio
from dataclasses import dataclass
import logging
import re
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message, ReactionTypeEmoji, ReplyKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.menu import (
    MAIN_MENU_TEXT,
    HELP_MENU_TEXT,
    PERIOD_MENU_TEXT,
    SETTINGS_MENU_TEXT,
    activity_settings_keyboard,
    help_menu_keyboard,
    main_menu_keyboard,
    period_menu_keyboard,
    settings_menu_keyboard,
    sex_settings_keyboard,
)
from sqlalchemy import func, select

from app.config import get_settings
from app.database import async_session_maker
from app.models import Food, MealLog, ReminderSettings, StandardMeal, User, WeightLog
from app.services.access import is_admin, is_allowed_telegram_user
from app.services.nutrition import (
    create_standard_meal_from_text,
    find_standard_meal,
    format_logged_meal,
    infer_meal_type,
    log_food_text,
    log_standard_meal,
    normalize_standard_meal_name,
    save_standard_meal_from_totals,
)
from app.services.openai_food_analyzer import FoodVisionAnalysis, analyze_food_image
from app.services.openai_dialog import DialogDecision, DialogFoodEstimate, interpret_dialog_message
from app.services.recommendations import recommend_next_meal
from app.services.dietitian_qa import answer_dietitian_question
from app.services.reminders import schedule_user_reminders
from app.services.reports import (
    build_all_time_report,
    build_daily_report,
    build_monthly_report,
    build_weekly_report,
    build_year_report,
    format_daily_report,
    format_daily_summary,
)
from app.services.weekly_score_image import render_weekly_score_target
from app.services.weekly_report_formatter import (
    format_all_time_report_html,
    format_weekly_report_html,
    format_year_report_html,
)
from app.services.users import get_or_create_user
from app.schemas import MICRONUTRIENT_KEYS
from app.text import fix_text

logger = logging.getLogger(__name__)
router = Router()
pending_weight_users: set[int] = set()
pending_settings_users: set[int] = set()
pending_standard_meal_users: set[int] = set()
pending_change_users: set[int] = set()
pending_support_users: set[int] = set()
pending_settings_field_users: dict[int, str] = {}


@dataclass
class PendingPhotoCorrection:
    meal_log_id: int
    image_bytes: bytes
    expires_at: datetime
    caption: str | None = None


@dataclass
class TargetProposal:
    calories: float
    protein: float
    fat: float
    carbs: float


PHOTO_CORRECTION_WINDOW = timedelta(minutes=5)
pending_photo_corrections: dict[int, PendingPhotoCorrection] = {}
pending_target_proposals: dict[int, TargetProposal] = {}


DISCLAIMER = "Это оценочный пищевой дневник, не медицинская диагностика."
STANDARD_MEAL_EXAMPLE = "обед 1; гречка 150 г, курица 120 г"
STANDARD_MEAL_NAME_RE = re.compile(
    r"^\s*(?P<meal>завтрак|обед|ужин|перекус)\s*(?P<number>\d+)?"
    r"(?P<sep>[\s:;,.!?()\[\]{}<>'\"«»/\\|+=_*~#№—–-]+)"
    r"(?P<ingredients>.+?)\s*$",
    re.IGNORECASE,
)
FOOD_REACTION_KEYWORDS = (
    "авокад",
    "бургер",
    "сэндвич",
    "бутерброд",
    "тост",
    "яйц",
    "омлет",
    "каша",
    "греч",
    "рис",
    "перлов",
    "овсян",
    "паста",
    "макарон",
    "картоф",
    "куриц",
    "индей",
    "говяд",
    "свин",
    "котлет",
    "рыб",
    "лосос",
    "семг",
    "сёмг",
    "кревет",
    "творог",
    "сыр",
    "йогурт",
    "кефир",
    "молок",
    "сметан",
    "салат",
    "суп",
    "овощ",
    "помид",
    "огур",
    "капуст",
    "морков",
    "свек",
    "руккол",
    "шпинат",
    "фасол",
    "чечев",
    "нут",
    "эдамам",
    "орех",
    "хлеб",
    "булоч",
    "круас",
    "печень",
    "шокол",
    "ягод",
    "череш",
    "вишн",
    "яблок",
    "банан",
    "апельс",
    "мандар",
    "абрикос",
    "персик",
    "кофе",
    "латте",
    "матча",
    "чай",
    "сок",
    "лимонад",
)
SEX_LABELS = {
    "female": "женский",
    "male": "мужской",
}
SEX_ALIASES = {
    "ж": "female",
    "жен": "female",
    "женский": "female",
    "женщина": "female",
    "female": "female",
    "f": "female",
    "м": "male",
    "муж": "male",
    "мужской": "male",
    "мужчина": "male",
    "male": "male",
    "m": "male",
}
ACTIVITY_LEVELS = {
    "low": ("низкая", 1.2),
    "light": ("лёгкая", 1.375),
    "moderate": ("средняя", 1.55),
    "high": ("высокая", 1.725),
    "very_high": ("очень высокая", 1.9),
}
ACTIVITY_ALIASES = {
    "низкая": "low",
    "низкий": "low",
    "низкая активность": "low",
    "сидячая": "low",
    "мало": "low",
    "минимальная": "low",
    "легкая": "light",
    "легкий": "light",
    "лёгкая": "light",
    "легкая активность": "light",
    "лёгкая активность": "light",
    "средняя": "moderate",
    "средний": "moderate",
    "средняя активность": "moderate",
    "умеренная": "moderate",
    "умеренный": "moderate",
    "обычная": "moderate",
    "высокая": "high",
    "высокий": "high",
    "высокая активность": "high",
    "активная": "high",
    "очень высокая": "very_high",
    "очень высокий": "very_high",
    "очень активная": "very_high",
}
SETTINGS_FIELD_PREFIXES = (
    "вес ",
    "мой вес ",
    "вес сейчас ",
    "текущий вес ",
    "желаемый вес ",
    "целевой вес ",
    "цель по весу ",
    "рост ",
    "возраст ",
    "пол ",
    "активность ",
)
SETTINGS_UPDATE_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("target_weight_kg", ("желаемый вес", "целевой вес", "цель по весу")),
    ("current_weight_kg", ("текущий вес", "вес сейчас", "мой вес", "вес")),
    ("activity_level", ("активность",)),
    ("height_cm", ("рост",)),
    ("age_years", ("возраст",)),
    ("sex", ("пол",)),
)


async def _react_food_logged(message: Message) -> None:
    try:
        await message.react([ReactionTypeEmoji(emoji="🎉")], is_big=True)
    except Exception as exc:
        logger.debug("Could not set food log reaction: %s", exc)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        latest_weight = await _latest_weight_log(session, user)
    needs_settings = _needs_settings_profile(user, latest_weight)
    await message.answer(
        f"Привет. Я помогу вести питание короткими записями.\n{DISCLAIMER}\n\n"
        "Можно написать: «гречка 150 г, курица 120 г», выбрать шаблон вроде «обед 1» "
        "или отправить фото еды.\n\n"
        "Основные действия есть в кнопках меню."
    )

    if needs_settings:
        pending_settings_users.add(message.from_user.id)
        await message.answer(
            "Давай один раз настроим профиль, чтобы я мог считать рекомендованные калории.\n\n"
            f"{_settings_onboarding_help()}",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    pending_settings_users.discard(message.from_user.id)
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    help_text = (
        "Как пользоваться\n\n"
        "Записать еду: напиши продукты и граммы, например:\n"
        "гречка 150 г, курица 120 г\n\n"
        "Фото: отправь фото еды, я сразу запишу оценку.\n\n"
        "Шаблоны: нажми «Шаблоны» или напиши название шаблона, например: обед 1.\n\n"
        "Исправить запись: нажми «Изменить» и напиши правку обычными словами.\n\n"
        "Отчеты: день, неделя, месяц, год и всё время.\n\n"
        "Настройки: профиль, вес и цель, дневная норма, лимиты КБЖУ, напоминания.\n\n"
        "Помощь: изменить запись или обратиться в поддержку."
    )
    await message.answer(help_text, reply_markup=main_menu_keyboard())


@router.message(Command("support"))
async def cmd_support(message: Message) -> None:
    _clear_pending_input_states(message.from_user.id)
    pending_support_users.add(message.from_user.id)
    await message.answer(
        "Напиши сообщение в поддержку одним следующим сообщением.\n\n"
        "Можно описать проблему, приложить текст ошибки или отправить скриншот.\n"
        "Чтобы выйти из этого режима, нажми «Назад».",
        reply_markup=help_menu_keyboard(),
    )


@router.message(Command("reply"))
async def cmd_reply(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Команда /reply доступна только администратору.", reply_markup=main_menu_keyboard())
        return

    payload = _command_payload(message.text or "")
    parts = payload.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /reply TELEGRAM_ID текст ответа")
        return

    try:
        telegram_id = int(parts[0])
    except ValueError:
        await message.answer("Telegram ID должен быть числом.")
        return

    reply_text = parts[1].strip()
    if not reply_text:
        await message.answer("Текст ответа пустой.")
        return

    await bot.send_message(
        telegram_id,
        f"Поддержка:\n\n{reply_text}",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer("Ответ отправлен пользователю от имени бота.")


def _clear_pending_input_states(user_id: int) -> None:
    pending_weight_users.discard(user_id)
    pending_settings_users.discard(user_id)
    pending_settings_field_users.pop(user_id, None)
    pending_standard_meal_users.discard(user_id)
    pending_change_users.discard(user_id)
    pending_target_proposals.pop(user_id, None)


def _is_support_request(lowered: str) -> bool:
    return lowered.strip().replace("ё", "е") in {
        "написать в поддержку",
        "обратиться в поддержку",
        "поддержка",
        "служба поддержки",
        "support",
    }


async def _send_support_message(message: Message, bot: Bot) -> None:
    settings = get_settings()
    admin_id = settings.telegram_admin_id
    if admin_id is None:
        await message.answer(
            "Поддержка пока не настроена. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    user = message.from_user
    username = f"@{user.username}" if user and user.username else "нет"
    full_name = html.escape(user.full_name if user else "без имени")
    support_header = (
        "Сообщение в поддержку\n\n"
        f"От: {full_name}\n"
        f"Telegram ID: <code>{user.id if user else 'unknown'}</code>\n"
        f"Username: {html.escape(username)}\n\n"
        f"Ответить: <code>/reply {user.id if user else ''} текст</code>"
    )

    try:
        await bot.send_message(admin_id, support_header, parse_mode="HTML")
        if message.text:
            await bot.send_message(
                admin_id,
                f"<b>Текст обращения:</b>\n{html.escape(message.text)}",
                parse_mode="HTML",
            )
        else:
            await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
    except Exception:
        logger.exception("Support message delivery failed")
        await message.answer(
            "Не получилось отправить сообщение в поддержку. Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "Сообщение отправлено в поддержку. Ответ придёт сюда в чат от бота.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    telegram_id = message.from_user.id
    if is_admin(telegram_id):
        status = "администратор"
    elif is_allowed_telegram_user(telegram_id):
        status = "разрешённый пользователь"
    else:
        status = "не в whitelist"

    await message.answer(
        f"Ваш Telegram ID: <code>{telegram_id}</code>\n"
        f"Статус: {status}",
        parse_mode="HTML",
    )


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Команда /users доступна только администратору.")
        return

    async with async_session_maker() as session:
        counts = (
            select(MealLog.user_id, func.count(MealLog.id).label("logs_count"))
            .group_by(MealLog.user_id)
            .subquery()
        )
        result = await session.execute(
            select(User, func.coalesce(counts.c.logs_count, 0))
            .outerjoin(counts, counts.c.user_id == User.id)
            .order_by(User.created_at)
        )
        rows = result.all()

    if not rows:
        await message.answer("Пользователей пока нет.")
        return

    lines = ["Пользователи:"]
    for user, logs_count in rows:
        name = user.name or "без имени"
        lines.append(
            f"{user.telegram_id} — {name}; записей: {logs_count}; "
            f"цели: {user.calorie_target:.0f} ккал, Б {user.protein_target:.0f}, "
            f"Ж {user.fat_target:.0f}, У {user.carb_target:.0f}; "
            f"вес-цель: {_format_target_weight(user)}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    payload = _command_payload(message.text or "")
    if payload:
        await _answer_settings(message, payload)
        return
    await _answer_settings_menu(message)


async def _answer_settings_menu(message: Message) -> None:
    await message.answer(SETTINGS_MENU_TEXT, reply_markup=settings_menu_keyboard())


async def _answer_settings(message: Message, payload: str = "") -> None:
    payload = payload.strip()
    if not payload:
        await _answer_settings_menu(message)
        return
    normalized_payload = payload.lower().replace("ё", "е")
    if normalized_payload in {"профиль", "вес и цель"}:
        await _answer_settings_menu(message)
        return
    settings_field = _settings_field_from_button(normalized_payload)
    if settings_field is not None:
        await _start_settings_field_input(message, settings_field)
        return
    update_payload = ""
    if not _is_weight_settings_open_payload(payload):
        update_payload = payload
    if not update_payload:
        await _answer_settings_menu(message)
        return

    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        if update_payload:
            error = await _update_settings_profile(session, user, update_payload)
            if error:
                await message.answer(
                    f"{error}\n\n{_weight_settings_update_help()}",
                    parse_mode="HTML",
                    reply_markup=settings_menu_keyboard(),
                )
                return
        latest_weight = await _latest_weight_log(session, user)
        if update_payload:
            missing = _missing_settings_fields(user, latest_weight)
            if missing:
                await message.answer(
                    _missing_settings_hint(missing),
                    parse_mode="HTML",
                    reply_markup=settings_menu_keyboard(),
                )
                return
            if not missing:
                proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight)
                if proposal is not None:
                    await message.answer(
                        _format_auto_targets_response("Настройки сохранены.", proposal),
                        reply_markup=settings_menu_keyboard(),
                    )
                    return
                await message.answer("Настройки сохранены.", reply_markup=settings_menu_keyboard())
                return
    await _answer_settings_menu(message)


async def _answer_profile_settings(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
    await message.answer(
        _format_profile_settings(user),
        parse_mode="HTML",
        reply_markup=settings_menu_keyboard(),
    )


async def _answer_weight_goal_settings(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        latest_weight = await _latest_weight_log(session, user)
    await message.answer(
        _format_weight_goal_settings(user, latest_weight),
        parse_mode="HTML",
        reply_markup=settings_menu_keyboard(),
    )


async def _answer_daily_norm_settings(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        latest_weight = await _latest_weight_log(session, user)
        missing = _missing_settings_fields(user, latest_weight)
        proposal = None
        if not missing:
            proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight, skip_if_current=True)
    prefix = "Дневная норма пересчитана по текущим настройкам.\n\n" if proposal is not None else ""
    await message.answer(
        prefix + _format_daily_norm_settings(user, latest_weight),
        parse_mode="HTML",
        reply_markup=settings_menu_keyboard(),
    )


async def _answer_targets_settings(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
    await message.answer(
        "Лимиты КБЖУ\n\n"
        "Сейчас:\n"
        f"Калории: {user.calorie_target:.0f} ккал\n"
        f"Белок: {user.protein_target:.0f} г\n"
        f"Жиры: {user.fat_target:.0f} г\n"
        f"Углеводы: {user.carb_target:.0f} г\n\n"
        "Чтобы изменить, отправь 4 числа одним сообщением:\n"
        "<code>1800 110 60 190</code>\n\n"
        "Где: калории, белок, жиры, углеводы.",
        parse_mode="HTML",
        reply_markup=settings_menu_keyboard(),
    )


SETTINGS_FIELD_BUTTONS = {
    "вес": "current_weight_kg",
    "текущий вес": "current_weight_kg",
    "мой вес": "current_weight_kg",
    "weight": "current_weight_kg",
    "настройки веса": "current_weight_kg",
    "записать вес": "current_weight_kg",
    "желаемый вес": "target_weight_kg",
    "целевой вес": "target_weight_kg",
    "рост": "height_cm",
    "возраст": "age_years",
    "пол": "sex",
    "активность": "activity_level",
}


def _settings_field_from_button(text: str) -> str | None:
    return SETTINGS_FIELD_BUTTONS.get(text.strip().lower().replace("ё", "е"))


async def _start_settings_field_input(message: Message, field: str) -> None:
    pending_settings_field_users[message.from_user.id] = field
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        latest_weight = await _latest_weight_log(session, user)
    text = _format_settings_field_prompt(field, user, latest_weight)
    if field == "sex":
        markup = sex_settings_keyboard()
    elif field == "activity_level":
        markup = activity_settings_keyboard()
    else:
        markup = settings_menu_keyboard()
    await message.answer(text, reply_markup=markup)


def _format_settings_field_prompt(field: str, user: User, latest_weight: WeightLog | None) -> str:
    current = _format_settings_field_value(field, user, latest_weight)
    examples = {
        "current_weight_kg": "Напиши новый вес числом, например: 105",
        "target_weight_kg": "Напиши желаемый вес, например: 100",
        "height_cm": "Напиши рост числом, например: 170",
        "age_years": "Напиши возраст числом, например: 39",
        "sex": "Выбери пол кнопкой.",
        "activity_level": "Выбери активность кнопкой.",
    }
    return f"{_settings_field_label(field)}\n\nСейчас: {current}\n\n{examples[field]}"


def _settings_field_label(field: str) -> str:
    return {
        "current_weight_kg": "Вес",
        "target_weight_kg": "Желаемый вес",
        "height_cm": "Рост",
        "age_years": "Возраст",
        "sex": "Пол",
        "activity_level": "Активность",
    }.get(field, "Настройка")


def _format_settings_field_value(field: str, user: User, latest_weight: WeightLog | None) -> str:
    if field == "current_weight_kg":
        return _format_current_weight(latest_weight)
    if field == "target_weight_kg":
        return _format_target_weight(user)
    if field == "height_cm":
        return _format_optional_number(user.height_cm, "см")
    if field == "age_years":
        return _format_optional_number(user.age_years, "лет")
    if field == "sex":
        return _format_sex(user.sex)
    if field == "activity_level":
        return _format_activity_level(user.activity_level)
    return "не задано"


async def _handle_settings_field_input(message: Message, text: str, field: str) -> None:
    lowered = text.strip().lower().replace("ё", "е")
    if lowered in {"назад", "отмена", "отменить", "меню"}:
        pending_settings_field_users.pop(message.from_user.id, None)
        await message.answer(SETTINGS_MENU_TEXT, reply_markup=settings_menu_keyboard())
        return

    value, error = _parse_settings_field_value(field, text)
    if error:
        await message.answer(error, reply_markup=_settings_field_retry_keyboard(field))
        return

    pending_settings_field_users.pop(message.from_user.id, None)
    assert value is not None
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        await _apply_settings_values(session, user, {field: value})
        latest_weight = await _latest_weight_log(session, user)
        missing = _missing_settings_fields(user, latest_weight)
        proposal = None
        if not missing:
            proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight)

    label = _settings_field_label(field)
    if proposal is not None:
        text_response = _format_auto_targets_response(f"{label} сохранён.", proposal)
    elif missing:
        text_response = f"{label} сохранён.\n\nОсталось заполнить: {', '.join(missing)}."
    else:
        text_response = f"{label} сохранён."
    await message.answer(text_response, reply_markup=settings_menu_keyboard())


def _settings_field_retry_keyboard(field: str) -> ReplyKeyboardMarkup:
    if field == "sex":
        return sex_settings_keyboard()
    if field == "activity_level":
        return activity_settings_keyboard()
    return settings_menu_keyboard()


def _command_payload(text: str) -> str:
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _is_weight_settings_open_payload(payload: str) -> bool:
    lowered = payload.strip().lower().replace("ё", "е")
    return lowered in {"вес", "мой вес", "weight", "настройки веса"}


def _weight_settings_update_help() -> str:
    return (
        "Можно менять одним сообщением или по одному параметру:\n"
        "<code>Вес 105 кг Желаемый вес 100 кг Рост 170 Возраст 39 Пол женский Активность низкая</code>\n\n"
        "Или отдельно:\n"
        "<code>Вес 68</code>\n"
        "<code>Желаемый вес 60</code>\n"
        "<code>Рост 170</code>\n"
        "<code>Возраст 39</code>\n"
        "<code>Пол женский</code>\n"
        "<code>Активность средняя</code>\n\n"
        "Активность: низкая, лёгкая, средняя, высокая или очень высокая."
    )


def _settings_onboarding_help() -> str:
    return (
        "Можно заполнить всё одним сообщением:\n"
        "<code>Вес 105 кг Желаемый вес 100 кг Рост 170 Возраст 39 Пол женский Активность низкая</code>\n\n"
        "Или отправлять по одному параметру:\n"
        "<code>Вес 105</code>\n"
        "<code>Желаемый вес 100</code>\n"
        "<code>Рост 170</code>\n"
        "<code>Возраст 39</code>\n"
        "<code>Пол женский</code>\n"
        "<code>Активность средняя</code>"
    )


def _missing_settings_hint(missing: list[str]) -> str:
    examples = {
        "Вес": "Вес 105",
        "Желаемый вес": "Желаемый вес 100",
        "Рост": "Рост 170",
        "Возраст": "Возраст 39",
        "Пол": "Пол женский",
        "Активность": "Активность низкая",
    }
    lines = [
        "Сохранил.",
        "Осталось заполнить: " + ", ".join(missing) + ".",
        "",
        "Можно одним сообщением:",
        "<code>" + " ".join(examples[item] for item in missing if item in examples) + "</code>",
    ]
    if "Активность" in missing:
        lines.extend(["", "Активность: низкая, лёгкая, средняя, высокая или очень высокая."])
    return "\n".join(lines)


def _format_settings(user: User, latest_weight: WeightLog | None) -> str:
    current_weight = _format_current_weight(latest_weight)
    current_weight_kg = latest_weight.weight_kg if latest_weight else None
    recommended_targets = _recommended_targets(user, latest_weight.weight_kg if latest_weight else None)
    maintenance = _maintenance_calorie_target(user, latest_weight.weight_kg if latest_weight else None)
    missing = _missing_settings_fields(user, latest_weight)
    recommended_line = "заполни " + ", ".join(missing) if missing else "не рассчитано"
    if recommended_targets is not None:
        recommended_line = f"{recommended_targets.calories:.0f} ккал/день"
    maintenance_line = "не рассчитано" if maintenance is None else f"{maintenance:.0f} ккал/день"
    goal_gap_line = ""
    if current_weight_kg is not None and user.target_weight_kg is not None:
        gap = current_weight_kg - user.target_weight_kg
        if abs(gap) < 0.1:
            goal_gap_line = "До желаемого веса: цель достигнута\n"
        elif gap > 0:
            goal_gap_line = f"До желаемого веса: {gap:.1f} кг\n"
        else:
            goal_gap_line = f"До желаемого веса: нужно набрать {abs(gap):.1f} кг\n"
    missing_line = f"\nНе хватает: {', '.join(missing)}\n\n" if missing else "\nПрофиль заполнен.\n\n"

    return (
        "Настройки\n\n"
        "Вес и цель\n"
        f"Текущий вес: {current_weight}\n"
        f"Желаемый вес: {_format_target_weight(user)}\n"
        f"{goal_gap_line}\n"
        "Профиль\n"
        f"Рост: {_format_optional_number(user.height_cm, 'см')}\n"
        f"Возраст: {_format_optional_number(user.age_years, 'лет')}\n"
        f"Пол: {_format_sex(user.sex)}\n"
        f"Активность: {_format_activity_level(user.activity_level)}\n"
        f"{missing_line}"
        "Дневная норма\n"
        f"Сейчас в дневнике: {user.calorie_target:.0f} ккал\n"
        f"БЖУ: Б {user.protein_target:.0f}, Ж {user.fat_target:.0f}, У {user.carb_target:.0f}\n"
        f"Поддержание: {maintenance_line}\n"
        f"Рекомендовано: {recommended_line}\n\n"
        "Как изменить\n"
        "Выбери кнопку ниже: Профиль, Вес и цель, Дневная норма или Лимиты КБЖУ."
    )


def _format_profile_settings(user: User) -> str:
    return (
        "Профиль\n\n"
        f"Рост: {_format_optional_number(user.height_cm, 'см')}\n"
        f"Возраст: {_format_optional_number(user.age_years, 'лет')}\n"
        f"Пол: {_format_sex(user.sex)}\n"
        f"Активность: {_format_activity_level(user.activity_level)}\n\n"
        "Как изменить\n"
        "<code>Рост 170</code>\n"
        "<code>Возраст 39</code>\n"
        "<code>Пол женский</code>\n"
        "<code>Активность средняя</code>\n\n"
        "Активность: низкая, лёгкая, средняя, высокая или очень высокая."
    )


def _format_weight_goal_settings(user: User, latest_weight: WeightLog | None) -> str:
    current_weight = _format_current_weight(latest_weight)
    current_weight_kg = latest_weight.weight_kg if latest_weight else None
    goal_gap_line = ""
    if current_weight_kg is not None and user.target_weight_kg is not None:
        gap = current_weight_kg - user.target_weight_kg
        if abs(gap) < 0.1:
            goal_gap_line = "До желаемого веса: цель достигнута\n"
        elif gap > 0:
            goal_gap_line = f"До желаемого веса: {gap:.1f} кг\n"
        else:
            goal_gap_line = f"До желаемого веса: нужно набрать {abs(gap):.1f} кг\n"

    return (
        "Вес и цель\n\n"
        f"Текущий вес: {current_weight}\n"
        f"Желаемый вес: {_format_target_weight(user)}\n"
        f"{goal_gap_line}\n"
        "Как изменить\n"
        "<code>Вес 68</code>\n"
        "<code>Желаемый вес 60</code>"
    )


def _format_daily_norm_settings(user: User, latest_weight: WeightLog | None) -> str:
    current_weight_kg = latest_weight.weight_kg if latest_weight else None
    recommended_targets = _recommended_targets(user, current_weight_kg)
    maintenance = _maintenance_calorie_target(user, current_weight_kg)
    missing = _missing_settings_fields(user, latest_weight)
    maintenance_line = "не рассчитано" if maintenance is None else f"{maintenance:.0f} ккал/день"
    recommended_line = "заполни " + ", ".join(missing) if missing else "не рассчитано"
    if recommended_targets is not None:
        recommended_line = f"{recommended_targets.calories:.0f} ккал/день"

    return (
        "Дневная норма\n\n"
        f"Сейчас в дневнике: {user.calorie_target:.0f} ккал\n"
        f"БЖУ: Б {user.protein_target:.0f}, Ж {user.fat_target:.0f}, У {user.carb_target:.0f}\n"
        f"Поддержание: {maintenance_line}\n"
        f"Рекомендовано: {recommended_line}\n\n"
        "Как пересчитать\n"
        "Заполни или измени профиль и весовые данные:\n"
        "<code>Вес 105 Желаемый вес 100 Рост 170 Возраст 39 Пол женский Активность низкая</code>\n\n"
        "После полного профиля я пересчитаю дневную норму автоматически. "
        "Если нужны свои числа, открой «Лимиты КБЖУ»."
    )


def _needs_settings_profile(user: User, latest_weight: WeightLog | None) -> bool:
    return bool(_missing_settings_fields(user, latest_weight))


def _missing_settings_fields(user: User, latest_weight: WeightLog | None) -> list[str]:
    missing = []
    if latest_weight is None:
        missing.append("Вес")
    if user.target_weight_kg is None:
        missing.append("Желаемый вес")
    if user.height_cm is None:
        missing.append("Рост")
    if user.age_years is None:
        missing.append("Возраст")
    if user.sex not in SEX_LABELS:
        missing.append("Пол")
    if user.activity_level not in ACTIVITY_LEVELS:
        missing.append("Активность")
    return missing


async def _update_settings_profile(session, user: User, payload: str) -> str | None:
    parsed, error = _parse_settings_update(payload)
    if error:
        return error
    assert parsed is not None

    await _apply_settings_values(session, user, parsed)
    return None


async def _apply_settings_values(
    session,
    user: User,
    parsed: dict[str, float | int | str],
) -> None:
    if "current_weight_kg" in parsed:
        session.add(WeightLog(user_id=user.id, date=date.today(), weight_kg=parsed["current_weight_kg"]))
    if "target_weight_kg" in parsed:
        user.target_weight_kg = parsed["target_weight_kg"]
    if "height_cm" in parsed:
        user.height_cm = parsed["height_cm"]
    if "age_years" in parsed:
        user.age_years = parsed["age_years"]
    if "sex" in parsed:
        user.sex = parsed["sex"]
    if "activity_level" in parsed:
        user.activity_level = parsed["activity_level"]
    await session.commit()
    await session.refresh(user)


def _parse_settings_update(payload: str) -> tuple[dict[str, float | int | str] | None, str | None]:
    matches = _settings_field_matches(payload)
    if matches:
        return _parse_labeled_settings_update(payload, matches)
    if ";" in payload:
        return _parse_settings_profile(payload)
    return _parse_single_settings_update(payload)


def _settings_field_matches(payload: str) -> list[re.Match[str]]:
    prefix_to_field = {
        prefix.replace("ё", "е"): field
        for field, prefixes in SETTINGS_UPDATE_FIELDS
        for prefix in prefixes
    }
    alternatives = sorted(prefix_to_field, key=len, reverse=True)
    pattern = r"(?<!\w)(" + "|".join(re.escape(prefix) for prefix in alternatives) + r")(?=\s|[:=;,.!?—–-]|$)"
    return list(re.finditer(pattern, payload.lower().replace("ё", "е"), re.IGNORECASE))


def _field_by_settings_prefix(prefix: str) -> str:
    normalized = prefix.lower().replace("ё", "е")
    for field, prefixes in SETTINGS_UPDATE_FIELDS:
        if normalized in {item.replace("ё", "е") for item in prefixes}:
            return field
    return ""


def _parse_labeled_settings_update(
    payload: str,
    matches: list[re.Match[str]],
) -> tuple[dict[str, float | int | str] | None, str | None]:
    parsed: dict[str, float | int | str] = {}
    for index, match in enumerate(matches):
        field = _field_by_settings_prefix(match.group(1))
        if not field:
            continue
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(payload)
        value = payload[match.end() : next_start].strip(" \t\n\r:=—–-,.;")
        if not value:
            return None, _settings_empty_value_error(field)
        parsed_value, error = _parse_settings_field_value(field, value)
        if error:
            return None, error
        parsed[field] = parsed_value

    if not parsed:
        return None, (
            "Не понял, какой параметр обновить. Напиши, например: "
            "Вес 105, Желаемый вес 100, Рост 170, Возраст 39, Пол женский или Активность средняя."
        )
    return parsed, None


def _settings_empty_value_error(field: str) -> str:
    examples = {
        "current_weight_kg": "Не понял текущий вес. Напиши так: Вес 105",
        "target_weight_kg": "Не понял желаемый вес. Напиши так: Желаемый вес 100",
        "height_cm": "Не понял рост. Напиши так: Рост 170",
        "age_years": "Не понял возраст. Напиши так: Возраст 39",
        "sex": "Пол можно указать так: Пол женский или Пол мужской",
        "activity_level": "Активность: низкая, лёгкая, средняя, высокая или очень высокая.",
    }
    return examples.get(field, "Не понял значение настройки.")


def _parse_settings_field_value(field: str, value: str) -> tuple[float | int | str | None, str | None]:
    if field == "current_weight_kg":
        weight = _parse_weight_value(value)
        if weight is None:
            return None, "Не понял текущий вес. Напиши так: Вес 105"
        return weight, None
    if field == "target_weight_kg":
        target_weight = _parse_weight_value(value)
        if target_weight is None:
            return None, "Не понял желаемый вес. Напиши так: Желаемый вес 100"
        return target_weight, None
    if field == "height_cm":
        height_cm = _parse_height_value(value)
        if height_cm is None:
            return None, "Не понял рост. Напиши так: Рост 170"
        return height_cm, None
    if field == "age_years":
        age_years = _parse_age_value(value)
        if age_years is None:
            return None, "Не понял возраст. Напиши так: Возраст 39"
        return age_years, None
    if field == "sex":
        sex = _normalize_sex(value)
        if sex is None:
            return None, "Пол можно указать так: Пол женский или Пол мужской"
        return sex, None
    if field == "activity_level":
        activity_level = _normalize_activity_level(value)
        if activity_level is None:
            return None, "Активность: низкая, лёгкая, средняя, высокая или очень высокая."
        return activity_level, None
    return None, "Не понял значение настройки."


def _parse_single_settings_update(payload: str) -> tuple[dict[str, float | int | str] | None, str | None]:
    value = _value_after_prefix(payload, ("вес", "мой вес", "вес сейчас", "текущий вес"))
    if value is not None:
        weight = _parse_weight_value(value)
        if weight is None:
            return None, "Не понял текущий вес. Напиши так: Вес 68"
        return {"current_weight_kg": weight}, None

    value = _value_after_prefix(payload, ("желаемый вес", "целевой вес", "цель по весу"))
    if value is not None:
        target_weight = _parse_weight_value(value)
        if target_weight is None:
            return None, "Не понял желаемый вес. Напиши так: Желаемый вес 60"
        return {"target_weight_kg": target_weight}, None

    value = _value_after_prefix(payload, ("рост",))
    if value is not None:
        height_cm = _parse_height_value(value)
        if height_cm is None:
            return None, "Не понял рост. Напиши так: Рост 170"
        return {"height_cm": height_cm}, None

    value = _value_after_prefix(payload, ("возраст",))
    if value is not None:
        age_years = _parse_age_value(value)
        if age_years is None:
            return None, "Не понял возраст. Напиши так: Возраст 39"
        return {"age_years": age_years}, None

    value = _value_after_prefix(payload, ("пол",))
    if value is not None:
        sex = _normalize_sex(value)
        if sex is None:
            return None, "Пол можно указать так: Пол женский или Пол мужской"
        return {"sex": sex}, None

    value = _value_after_prefix(payload, ("активность",))
    if value is not None:
        activity_level = _normalize_activity_level(value)
        if activity_level is None:
            return None, "Активность: низкая, лёгкая, средняя, высокая или очень высокая."
        return {"activity_level": activity_level}, None

    sex = _normalize_sex(payload)
    if sex is not None:
        return {"sex": sex}, None

    activity_level = _normalize_activity_level(payload)
    if activity_level is not None:
        return {"activity_level": activity_level}, None

    return None, (
        "Не понял, какой параметр обновить. Напиши, например: "
        "Вес 68, Желаемый вес 60, Рост 170, Возраст 39, Пол женский или Активность средняя."
    )


def _value_after_prefix(payload: str, prefixes: tuple[str, ...]) -> str | None:
    stripped = payload.strip()
    lowered = stripped.lower().replace("ё", "е")
    for prefix in prefixes:
        normalized_prefix = prefix.replace("ё", "е")
        if lowered == normalized_prefix:
            return ""
        if lowered.startswith(normalized_prefix + " "):
            return stripped[len(prefix) :].strip(" :=-—")
    return None


def _parse_settings_profile(payload: str) -> tuple[dict[str, float | int | str] | None, str | None]:
    parts = [part.strip() for part in re.split(r"[;\n]+", payload) if part.strip()]
    if len(parts) != 6:
        return None, "Нужно 6 значений через точку с запятой: текущий вес; желаемый вес; рост; возраст; пол; активность."

    current_weight = _parse_weight_value(parts[0])
    if current_weight is None:
        return None, "Не понял текущий вес. Пример: 107 или 107.4"

    target_weight = _parse_weight_value(parts[1])
    if target_weight is None:
        return None, "Не понял желаемый вес. Пример: 80"

    height_cm = _parse_height_value(parts[2])
    if height_cm is None:
        return None, "Не понял рост. Пример: 170"

    age_years = _parse_age_value(parts[3])
    if age_years is None:
        return None, "Не понял возраст. Пример: 39"

    sex = _normalize_sex(parts[4])
    if sex is None:
        return None, "Пол можно указать так: женский или мужской."

    activity_level = _normalize_activity_level(parts[5])
    if activity_level is None:
        return None, "Активность: низкая, лёгкая, средняя, высокая или очень высокая."

    return (
        {
            "current_weight_kg": current_weight,
            "target_weight_kg": target_weight,
            "height_cm": height_cm,
            "age_years": age_years,
            "sex": sex,
            "activity_level": activity_level,
        },
        None,
    )


def _normalize_sex(text: str) -> str | None:
    return SEX_ALIASES.get(text.strip().lower().replace("ё", "е"))


def _normalize_activity_level(text: str) -> str | None:
    key = text.strip().lower().replace("ё", "е")
    return ACTIVITY_ALIASES.get(key)


def _format_current_weight(weight_log: WeightLog | None) -> str:
    if weight_log is None:
        return "не записан"
    return f"{weight_log.weight_kg:.1f} кг ({weight_log.date:%d.%m.%Y})"


def _format_optional_number(value: float | int | None, unit: str) -> str:
    if value is None:
        return "не задан"
    if isinstance(value, float) and value.is_integer():
        return f"{value:.0f} {unit}"
    return f"{value} {unit}"


def _format_sex(value: str | None) -> str:
    if value is None:
        return "не задан"
    return SEX_LABELS.get(value, value)


def _format_activity_level(value: str | None) -> str:
    if value is None:
        return "не задана"
    level = ACTIVITY_LEVELS.get(value)
    if not level:
        return value
    return f"{level[0]} (коэффициент {level[1]:.3g})"


async def _latest_weight_log(session, user: User) -> WeightLog | None:
    result = await session.execute(
        select(WeightLog)
        .where(WeightLog.user_id == user.id)
        .order_by(WeightLog.date.desc(), WeightLog.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _recommended_calorie_target(user: User, current_weight_kg: float | None) -> float | None:
    maintenance = _maintenance_calorie_target(user, current_weight_kg)
    if maintenance is None:
        return None

    recommended = maintenance
    if user.target_weight_kg is not None and current_weight_kg is not None:
        if user.target_weight_kg < current_weight_kg - 1:
            gap = current_weight_kg - user.target_weight_kg
            deficit = 0.10 if gap < 5 else 0.15
            recommended = maintenance * (1 - deficit)
        elif user.target_weight_kg > current_weight_kg + 1:
            recommended = maintenance * 1.10

    minimum = 1200 if user.sex == "female" else 1500
    return max(recommended, minimum)


def _recommended_targets(user: User, current_weight_kg: float | None) -> TargetProposal | None:
    calories = _recommended_calorie_target(user, current_weight_kg)
    if calories is None:
        return None

    reference_weight = user.target_weight_kg or current_weight_kg
    if reference_weight is None:
        return None

    protein_per_kg = 1.2 if user.sex == "female" else 1.4
    protein = _round_to_step(max(60, min(190, reference_weight * protein_per_kg)), 5)
    min_fat = 45 if user.sex == "female" else 55
    fat = _round_to_step(max(min_fat, min(110, calories * 0.30 / 9)), 5)
    carbs = _round_to_step(max(80, (calories - protein * 4 - fat * 9) / 4), 5)
    return TargetProposal(
        calories=_round_to_step(calories, 10),
        protein=protein,
        fat=fat,
        carbs=carbs,
    )


def _round_to_step(value: float, step: int) -> float:
    return round(value / step) * step


def _maintenance_calorie_target(user: User, current_weight_kg: float | None) -> float | None:
    if (
        current_weight_kg is None
        or user.height_cm is None
        or user.age_years is None
        or user.sex not in SEX_LABELS
        or user.activity_level not in ACTIVITY_LEVELS
    ):
        return None

    bmr = _estimate_bmr_mifflin_st_jeor(current_weight_kg, user.height_cm, user.age_years, user.sex)
    return bmr * ACTIVITY_LEVELS[user.activity_level][1]


def _estimate_bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age_years: int, sex: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age_years
    if sex == "female":
        return base - 161
    return base + 5


@router.message(Command("set_targets"))
async def cmd_set_targets(message: Message) -> None:
    parts = message.text.split()[1:]
    target_telegram_id: int | None = None
    target_parts = parts

    if len(parts) == 5:
        if not is_admin(message.from_user.id):
            await message.answer("Менять цели другого пользователя может только администратор.")
            return
        try:
            target_telegram_id = int(parts[0])
        except ValueError:
            await message.answer("Формат для администратора: /set_targets TELEGRAM_ID 1800 110 60 190")
            return
        target_parts = parts[1:]
    elif not parts:
        await message.answer(_targets_help_text(), parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    elif len(parts) != 4:
        await message.answer(_targets_help_text("Не получилось обновить дневную норму."), parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    parsed_targets, error = _parse_target_numbers(target_parts)
    if error:
        await message.answer(_targets_help_text(error), parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    assert parsed_targets is not None
    calories, protein, fat, carbs = parsed_targets

    async with async_session_maker() as session:
        if target_telegram_id is None:
            user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        else:
            user = await get_or_create_user(session, target_telegram_id)
        await _apply_target_values(session, user, calories, protein, fat, carbs)
    target_label = "" if target_telegram_id is None else f" для {target_telegram_id}"
    await message.answer(f"Дневная норма{target_label} обновлена: {calories:.0f} ккал, Б {protein:.0f}, Ж {fat:.0f}, У {carbs:.0f}.")


def _targets_help_text(intro: str | None = None) -> str:
    lines = []
    if intro:
        lines.extend([intro, ""])
    lines.extend(
        [
            "Дневная норма",
            "",
            "Чтобы изменить калории и БЖУ, напиши:",
            "<code>1800 110 60 190</code>",
            "",
            "Где:",
            "1800 — калории",
            "110 — белок",
            "60 — жиры",
            "190 — углеводы",
        ]
    )
    return "\n".join(lines)


def _targets_match_current(user: User, proposal: TargetProposal) -> bool:
    return (
        abs(user.calorie_target - proposal.calories) < 1
        and abs(user.protein_target - proposal.protein) < 1
        and abs(user.fat_target - proposal.fat) < 1
        and abs(user.carb_target - proposal.carbs) < 1
    )


async def _answer_target_proposal(
    message: Message,
    user: User,
    latest_weight: WeightLog | None,
    intro: str,
    *,
    skip_if_current: bool = False,
) -> bool:
    proposal = _recommended_targets(user, latest_weight.weight_kg if latest_weight else None)
    if proposal is None:
        return False
    if skip_if_current and _targets_match_current(user, proposal):
        return False

    pending_target_proposals[message.from_user.id] = proposal
    await message.answer(
        f"{intro}\n\n"
        "Рекомендованная дневная норма:\n"
        f"Калории: {proposal.calories:.0f}\n"
        f"Белок: {proposal.protein:.0f} г\n"
        f"Жиры: {proposal.fat:.0f} г\n"
        f"Углеводы: {proposal.carbs:.0f} г\n\n"
        "Ответь <b>Да</b>, чтобы применить.\n"
        "Или отправь свои значения, например:\n"
        "<code>1800 110 60 190</code>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return True


async def _apply_recommended_targets_if_ready(
    session,
    user: User,
    latest_weight: WeightLog | None,
    *,
    skip_if_current: bool = False,
) -> TargetProposal | None:
    proposal = _recommended_targets(user, latest_weight.weight_kg if latest_weight else None)
    if proposal is None:
        return None
    if skip_if_current and _targets_match_current(user, proposal):
        return None
    await _apply_target_values(session, user, proposal.calories, proposal.protein, proposal.fat, proposal.carbs)
    await session.refresh(user)
    return proposal


def _format_auto_targets_response(intro: str, proposal: TargetProposal) -> str:
    return (
        f"{intro}\n\n"
        "Дневная норма пересчитана:\n"
        f"Калории: {proposal.calories:.0f} ккал\n"
        f"Белок: {proposal.protein:.0f} г\n"
        f"Жиры: {proposal.fat:.0f} г\n"
        f"Углеводы: {proposal.carbs:.0f} г\n\n"
        "Если нужны свои числа, открой «Лимиты КБЖУ»."
    )


async def _apply_target_values(
    session,
    user: User,
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
) -> None:
    user.calorie_target = calories
    user.protein_target = protein
    user.fat_target = fat
    user.carb_target = carbs
    await session.commit()


async def _apply_pending_target_proposal(message: Message, proposal: TargetProposal) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        await _apply_target_values(session, user, proposal.calories, proposal.protein, proposal.fat, proposal.carbs)
    await message.answer(
        f"Дневная норма применена: {proposal.calories:.0f} ккал, "
        f"Б {proposal.protein:.0f}, Ж {proposal.fat:.0f}, У {proposal.carbs:.0f}.",
        reply_markup=main_menu_keyboard(),
    )


def _parse_target_numbers(parts: list[str]) -> tuple[tuple[float, float, float, float] | None, str | None]:
    if len(parts) != 4:
        return None, "Нужно 4 числа: калории, белок, жиры, углеводы."
    try:
        calories, protein, fat, carbs = [float(part.replace(",", ".")) for part in parts]
    except ValueError:
        return None, "Не разобрал числа."
    if not 800 <= calories <= 5000:
        return None, "Калории должны быть похожи на дневную норму, например 1800."
    if not 0 <= protein <= 400 or not 0 <= fat <= 300 or not 0 <= carbs <= 700:
        return None, "БЖУ выглядит слишком необычно. Пример: 1800 110 60 190."
    return (calories, protein, fat, carbs), None


@router.message(Command("set_weight_target"))
async def cmd_set_weight_target(message: Message) -> None:
    parts = message.text.split()[1:]
    target_telegram_id: int | None = None
    target_parts = parts

    if len(parts) == 2:
        if not is_admin(message.from_user.id):
            await message.answer("Менять желаемый вес другого пользователя может только администратор.")
            return
        try:
            target_telegram_id = int(parts[0])
        except ValueError:
            await message.answer("Формат для администратора: /set_weight_target TELEGRAM_ID 68")
            return
        target_parts = parts[1:]
    elif len(parts) != 1:
        await message.answer("Формат: /set_weight_target 68")
        return

    try:
        target_weight = float(target_parts[0].replace(",", "."))
    except ValueError:
        await message.answer("Вес нужен числом. Пример: /set_weight_target 68")
        return

    if not 30 <= target_weight <= 250:
        await message.answer("Проверь число: ожидаю вес от 30 до 250 кг.")
        return

    async with async_session_maker() as session:
        if target_telegram_id is None:
            user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        else:
            user = await get_or_create_user(session, target_telegram_id)
        user.target_weight_kg = target_weight
        await session.commit()
        await session.refresh(user)
        if target_telegram_id is None:
            latest_weight = await _latest_weight_log(session, user)
            missing = _missing_settings_fields(user, latest_weight)
            if not missing:
                proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight)
                if proposal is not None:
                    await message.answer(
                        _format_auto_targets_response(f"Желаемый вес обновлён: {target_weight:.1f} кг.", proposal),
                        reply_markup=main_menu_keyboard(),
                    )
                    return

    target_label = "" if target_telegram_id is None else f" для {target_telegram_id}"
    await message.answer(f"Желаемый вес{target_label} обновлён: {target_weight:.1f} кг.")


@router.message(Command("add_food"))
async def cmd_add_food(message: Message) -> None:
    payload = message.text.removeprefix("/add_food").strip()
    parts = [part.strip() for part in payload.split(";")]
    if len(parts) < 6:
        await message.answer("Формат: /add_food название;ккал;б;ж;у;клетчатка")
        return
    name = parts[0].lower()
    try:
        calories, protein, fat, carbs, fiber = [float(part.replace(",", ".")) for part in parts[1:6]]
    except ValueError:
        await message.answer("Числа не разобрал. Пример: /add_food кефир;50;3;2.5;4;0")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(Food).where(Food.name == name))
        food = result.scalar_one_or_none()
        if food is None:
            food = Food(name=name, source="user")
            session.add(food)
        food.calories_per_100g = calories
        food.protein_per_100g = protein
        food.fat_per_100g = fat
        food.carbs_per_100g = carbs
        food.fiber_per_100g = fiber
        await session.commit()
    await message.answer(f"Добавил продукт: {name}.")


@router.message(Command("add_standard_meal"))
async def cmd_add_standard_meal(message: Message) -> None:
    payload = message.text.removeprefix("/add_standard_meal").strip()
    if _split_standard_meal_payload(payload) is None:
        pending_standard_meal_users.add(message.from_user.id)
    await _create_standard_meal_from_payload(message, payload)


async def _answer_standard_meal_help(message: Message, intro: str) -> None:
    await message.answer(
        f"{intro}\n\n"
        "Отправь одной строкой:\n"
        "<code>шаблон завтрак творог 150 г, ягоды 80 г</code>\n"
        "<code>шаблон обед салат 250 г, курица 120 г</code>\n"
        "<code>шаблон завтрак авокадо-бургер 300 ккал</code>\n\n"
        "Без слова <code>шаблон</code> я считаю сообщение обычным приёмом пищи.\n"
        "Если номер не указан, я сохраню следующий: <code>завтрак 1</code>, <code>завтрак 2</code> и т.д.\n"
        "Чтобы заменить шаблон, укажи номер:\n"
        "<code>шаблон завтрак 1 творог 200 г, ягоды 100 г</code>\n\n"
        "После сохранения можно записывать шаблон обычным сообщением: <code>завтрак 1</code>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


def _split_standard_meal_payload(payload: str) -> tuple[str, str] | None:
    cleaned = payload.strip()
    if not cleaned:
        return None

    if ";" in cleaned:
        name, ingredients = [part.strip() for part in cleaned.split(";", 1)]
    else:
        match = STANDARD_MEAL_NAME_RE.match(cleaned)
        if not match:
            return None
        meal = match.group("meal").lower()
        number = match.group("number")
        if number is None and re.fullmatch(r"\d+", match.group("ingredients").strip()):
            return None
        name = f"{meal} {number}".strip() if number else meal
        ingredients = match.group("ingredients").strip()

    ingredients = ingredients.strip(" :;,.!?()[]{}<>\"'«»")
    if not name or not ingredients:
        return None
    return name, ingredients


def _standard_meal_base_and_number(name: str) -> tuple[str, int | None] | None:
    normalized = normalize_standard_meal_name(name)
    match = re.fullmatch(r"(завтрак|обед|ужин|перекус)(?:\s+(\d+))?", normalized)
    if not match:
        return None
    number = int(match.group(2)) if match.group(2) else None
    return match.group(1), number


async def _resolve_standard_meal_name(session, user: User, name: str) -> tuple[str, bool]:
    parsed_name = _standard_meal_base_and_number(name)
    if parsed_name is None:
        return normalize_standard_meal_name(name), False

    base, number = parsed_name
    if number is not None:
        return f"{base} {number}", False

    result = await session.execute(select(StandardMeal).where(StandardMeal.user_id == user.id))
    max_number = 0
    for meal in result.scalars().all():
        existing = _standard_meal_base_and_number(meal.name)
        if existing is None:
            continue
        existing_base, existing_number = existing
        if existing_base != base:
            continue
        max_number = max(max_number, existing_number or 1)
    return f"{base} {max_number + 1}", True


async def _create_standard_meal_from_payload(message: Message, payload: str) -> bool:
    parsed = _split_standard_meal_payload(payload)
    if parsed is None:
        await _answer_standard_meal_help(message, "Формат шаблона: название и продукты с граммами.")
        return False
    name, ingredients = parsed
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        name, auto_numbered = await _resolve_standard_meal_name(session, user, name)
        existed_before = await find_standard_meal(session, user, name) is not None
        meal = await _create_standard_meal_from_explicit_nutrition(session, user, name, ingredients)
        if not meal:
            meal = await create_standard_meal_from_text(session, user, name, ingredients)
        if not meal:
            meal = await _create_standard_meal_from_openai_or_calories(session, user, name, ingredients)
    if not meal:
        await message.answer(
            "Не смог посчитать шаблон. Напиши продукты с граммами или хотя бы калорийность, например: завтрак 1 - авокадо-бургер 300 ккал.",
            reply_markup=main_menu_keyboard(),
        )
        return False
    action = "Шаблон обновлён" if existed_before and not auto_numbered else "Шаблон сохранён"
    await message.answer(
        f"{action}: {meal.name} — {meal.total_calories:.0f} ккал, "
        f"Б {meal.total_protein:.0f}, Ж {meal.total_fat:.0f}, У {meal.total_carbs:.0f}.",
        reply_markup=main_menu_keyboard(),
    )
    return True


@dataclass
class ExplicitNutrition:
    calories: float
    protein: float = 0
    fat: float = 0
    carbs: float = 0
    fiber: float = 0
    sodium: float = 0


def _number_from_text(value: str) -> float:
    return float(value.replace(",", "."))


def _extract_labeled_grams(text: str, labels: tuple[str, ...]) -> float | None:
    lowered = fix_text(text).lower().replace("ё", "е")
    label_pattern = "|".join(re.escape(label) for label in labels)
    pattern = rf"(?<!\w)(?:{label_pattern})(?!\w)\s*(?:[:=-]|—|–)?\s*(\d+(?:[,.]\d+)?)\s*(?:г|g)\b"
    match = re.search(pattern, lowered, re.IGNORECASE)
    return _number_from_text(match.group(1)) if match else None


def _extract_explicit_nutrition(text: str) -> ExplicitNutrition | None:
    calories = _extract_explicit_calories(text)
    if calories is None:
        return None

    protein = _extract_labeled_grams(text, ("белки", "белок", "б"))
    fat = _extract_labeled_grams(text, ("жиры", "жир", "ж"))
    carbs = _extract_labeled_grams(text, ("углеводы", "углевод", "у"))
    fiber = _extract_labeled_grams(text, ("клетчатка", "пищевые волокна"))
    salt = _extract_labeled_grams(text, ("соль",))

    return ExplicitNutrition(
        calories=calories,
        protein=protein or 0,
        fat=fat or 0,
        carbs=carbs or 0,
        fiber=fiber or 0,
        sodium=(salt or 0) * 393.4,
    )


def _explicit_nutrition_description(text: str, nutrition: ExplicitNutrition) -> str:
    cleaned = fix_text(text).strip()
    has_macros = any([nutrition.protein, nutrition.fat, nutrition.carbs, nutrition.fiber])
    if not has_macros:
        cleaned = re.sub(
            r"\s+а\s+не\s+\d{2,4}(?:[,.]\d+)?\s*(?:ккал|кал(?:\.|орий|ории)?)\b.*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(?:там|должно быть|исправь|исправленная калорийность)\s*[:,-]*\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned or f"{nutrition.calories:.0f} ккал"


async def _create_standard_meal_from_explicit_nutrition(
    session,
    user: User,
    name: str,
    ingredients: str,
) -> StandardMeal | None:
    nutrition = _extract_explicit_nutrition(ingredients)
    if nutrition is None:
        return None

    micros = {key: 0.0 for key in MICRONUTRIENT_KEYS}
    micros["sodium"] = nutrition.sodium
    return await save_standard_meal_from_totals(
        session,
        user,
        name,
        _explicit_nutrition_description(ingredients, nutrition),
        nutrition.calories,
        nutrition.protein,
        nutrition.fat,
        nutrition.carbs,
        nutrition.fiber,
        micros,
    )


async def _create_standard_meal_from_openai_or_calories(
    session,
    user: User,
    name: str,
    ingredients: str,
) -> StandardMeal | None:
    decision = await interpret_dialog_message(session, user, ingredients)
    estimate = decision.food if decision and decision.food and decision.food.calories > 0 else None
    if estimate is not None:
        return await save_standard_meal_from_totals(
            session,
            user,
            name,
            _dialog_estimate_notes(estimate),
            estimate.calories,
            estimate.protein,
            estimate.fat,
            estimate.carbs,
            estimate.fiber,
            _normalize_dialog_micros(estimate),
        )

    calories = _extract_explicit_calories(ingredients)
    if calories is None:
        return None
    description = re.sub(r"\b\d+(?:[,.]\d+)?\s*(?:ккал|кал(?:\.|орий|ории)?)\b", "", ingredients, flags=re.IGNORECASE)
    description = description.strip(" :;,.!?()[]{}<>\"'«»—–-") or ingredients.strip()
    return await save_standard_meal_from_totals(
        session,
        user,
        name,
        f"{description} - {calories:.0f} ккал",
        calories,
        0,
        0,
        0,
        0,
        {key: 0.0 for key in MICRONUTRIENT_KEYS},
    )


@router.message(Command("list_meals"))
async def cmd_list_meals(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        result = await session.execute(select(StandardMeal).where(StandardMeal.user_id == user.id).order_by(StandardMeal.name))
        meals = list(result.scalars().all())
    if not meals:
        await _answer_standard_meal_help(message, "Шаблонов пока нет.")
        return
    await message.answer(
        "Шаблоны:\n"
        + "\n".join(f"{meal.name} — {meal.total_calories:.0f} ккал — {meal.description}" for meal in meals)
        + "\n\nЗаписать в дневник: отправь только название, например: завтрак 1."
        + "\nСоздать новый: шаблон завтрак творог 150 г, ягоды 80 г — номер поставлю сама."
        + "\nЗаменить существующий: шаблон завтрак 1 творог 200 г, ягоды 100 г.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("log_weight"))
async def cmd_log_weight(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        pending_weight_users.add(message.from_user.id)
        await message.answer(
            "Напиши вес одним числом, например: 107 или 107.4",
            reply_markup=main_menu_keyboard(),
        )
        return
    weight = _parse_weight_value(parts[1])
    if weight is None:
        pending_weight_users.add(message.from_user.id)
        await message.answer(
            "Вес нужен числом. Можно так: /log_weight 107",
            reply_markup=main_menu_keyboard(),
        )
        return
    await _save_weight(message, weight)


async def _save_weight(message: Message, weight: float) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        session.add(WeightLog(user_id=user.id, date=date.today(), weight_kg=weight))
        await session.commit()
        await session.refresh(user)
        latest_weight = await _latest_weight_log(session, user)
        missing = _missing_settings_fields(user, latest_weight)
        if not missing:
            proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight, skip_if_current=True)
            if proposal is not None:
                await message.answer(
                    _format_auto_targets_response(f"Вес записан: {weight:.1f} кг.", proposal),
                    reply_markup=main_menu_keyboard(),
                )
                return
    await message.answer(f"Вес записан: {weight:.1f} кг.", reply_markup=main_menu_keyboard())


def _parse_weight_value(text: str) -> float | None:
    cleaned = text.strip().lower().replace(",", ".")
    cleaned = cleaned.replace("кг", "").replace("килограмм", "").strip()
    match = re.search(r"(\d{2,3}(?:\.\d{1,2})?)", cleaned)
    if not match:
        return None
    weight = float(match.group(1))
    if 30 <= weight <= 250:
        return weight
    return None


def _parse_height_value(text: str) -> float | None:
    cleaned = text.strip().lower().replace(",", ".")
    cleaned = cleaned.replace("см", "").replace("сантиметр", "").strip()
    match = re.search(r"(\d{2,3}(?:\.\d{1,2})?)", cleaned)
    if not match:
        return None
    height = float(match.group(1))
    if 120 <= height <= 230:
        return height
    return None


def _parse_age_value(text: str) -> int | None:
    match = re.search(r"\d{1,3}", text)
    if not match:
        return None
    age_years = int(match.group(0))
    if 18 <= age_years <= 120:
        return age_years
    return None


def _format_target_weight(user: User) -> str:
    if user.target_weight_kg is None:
        return "не задан"
    return f"{user.target_weight_kg:.1f} кг"


async def _get_user_by_telegram_id(session, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def _resolve_report_user(message: Message, session, command: str) -> User | None:
    parts = message.text.split()[1:]
    if len(parts) > 1:
        await message.answer(f"Формат: /{command} или /{command} TELEGRAM_ID")
        return None

    if not parts:
        return await get_or_create_user(session, message.from_user.id, message.from_user.full_name)

    if not is_admin(message.from_user.id):
        await message.answer("Просмотр данных другого пользователя доступен только администратору.")
        return None

    try:
        telegram_id = int(parts[0])
    except ValueError:
        await message.answer(f"Telegram ID должен быть числом. Пример: /{command} 123456789")
        return None

    user = await _get_user_by_telegram_id(session, telegram_id)
    if user is None:
        await message.answer(f"Пользователь {telegram_id} пока не найден. Проверьте /users.")
        return None
    return user


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _resolve_report_user(message, session, "today")
        if user is None:
            return
        report = await build_daily_report(session, user)
    await message.answer(format_daily_report(report))


@router.message(Command("activity"))
async def cmd_activity(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _resolve_report_user(message, session, "activity")
        if not user:
            return
        report = await build_daily_report(session, user)
    if not any([report.steps, report.active_calories, report.total_burned_calories, report.sleep_minutes, report.avg_heart_rate]):
        await message.answer("Активность за сегодня пока не синхронизировалась. Проверь Health Connect companion на телефоне.")
        return
    lines = ["Активность за сегодня:"]
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
    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard())


@router.message(Command("week"))
async def cmd_week(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _resolve_report_user(message, session, "week")
        if user is None:
            return
        report = await build_weekly_report(session, user)
    await _answer_weekly_report(message, report)


@router.message(Command("month"))
async def cmd_month(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _resolve_report_user(message, session, "month")
        if user is None:
            return
        report = await build_monthly_report(session, user)
    await _answer_period_report(message, report, "месяца", "monthly")


@router.message(Command("year"))
async def cmd_year(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _resolve_report_user(message, session, "year")
        if user is None:
            return
        report = await build_year_report(session, user)
    await message.answer(format_year_report_html(report), parse_mode="HTML")
    if report.score > 0:
        score = max(1, min(10, int(report.score)))
        image = BufferedInputFile(
            render_weekly_score_target(score),
            filename=f"year-score-{score}.png",
        )
        await message.answer_photo(image, caption=f"Оценка года: {score}/10", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Картинка цели появится, когда за год будет хотя бы одна запись.", reply_markup=main_menu_keyboard())


@router.message(Command("all_time"))
async def cmd_all_time(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _resolve_report_user(message, session, "all_time")
        if user is None:
            return
        report = await build_all_time_report(session, user)
    await _answer_all_time_report(message, report)


async def _answer_all_time_report(message: Message, report) -> None:
    await message.answer(format_all_time_report_html(report), parse_mode="HTML")
    if report.score > 0:
        score = max(1, min(10, int(report.score)))
        image = BufferedInputFile(
            render_weekly_score_target(score),
            filename=f"all-time-score-{score}.png",
        )
        await message.answer_photo(image, caption=f"Оценка за все время: {score}/10", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Картинка цели появится, когда будет хотя бы одна запись еды.", reply_markup=main_menu_keyboard())


async def _answer_weekly_report(message: Message, report) -> None:
    await _answer_period_report(message, report, "недели", "weekly")


async def _answer_period_report(message: Message, report, caption_label: str, filename_prefix: str) -> None:
    score = max(1, min(10, int(report.score or 1)))
    await message.answer(format_weekly_report_html(report), parse_mode="HTML")
    image = BufferedInputFile(
        render_weekly_score_target(score),
        filename=f"{filename_prefix}-score-{score}.png",
    )
    await message.answer_photo(image, caption=f"Оценка {caption_label}: {score}/10", reply_markup=main_menu_keyboard())


@router.message(Command("undo", "delete_last"))
async def cmd_undo(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        result = await session.execute(
            select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.datetime.desc()).limit(1)
        )
        meal_log = result.scalar_one_or_none()
        if not meal_log:
            await message.answer("Пока нечего отменять.", reply_markup=main_menu_keyboard())
            return
        summary = format_logged_meal(meal_log, prefix="Отменил последнюю запись")
        await session.delete(meal_log)
        await session.commit()
    await message.answer(summary, reply_markup=main_menu_keyboard())


async def _start_change_mode(message: Message, prompt: str | None = None) -> None:
    pending_change_users.add(message.from_user.id)
    await message.answer(
        prompt
        or "Напиши, что изменить. Например: «в последнем обеде не свекла, а помидоры 120 г» или «замени калорийность последней записи на 650 ккал».",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("advice"))
async def cmd_advice(message: Message) -> None:
    await _answer_recommendation(message)


@router.message(Command("ask"))
async def cmd_ask(message: Message) -> None:
    question = message.text.removeprefix("/ask").strip()
    if not question:
        await message.answer("Напиши вопрос после команды. Например: /ask что лучше съесть на ужин?")
        return
    await _answer_free_question(message, question)


@router.message(Command("reminders"))
async def cmd_reminders(message: Message, bot: Bot, scheduler: AsyncIOScheduler | None = None) -> None:
    parts = message.text.split()[1:]
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        result = await session.execute(select(ReminderSettings).where(ReminderSettings.user_id == user.id))
        reminders = result.scalar_one_or_none()
        if reminders is None:
            reminders = ReminderSettings(user_id=user.id)
            session.add(reminders)

        action = parts[0].lower().replace("ё", "е") if parts else ""
        if action in {"off", "выкл", "выключить", "отключить"} and len(parts) == 1:
            reminders.enabled = False
        elif action in {"on", "вкл", "включить"} and len(parts) == 1:
            reminders.enabled = True
        elif len(parts) in {3, 4}:
            try:
                reminders.breakfast_time, reminders.lunch_time, reminders.dinner_time = [
                    _parse_hhmm(part) for part in parts[:3]
                ]
                reminders.evening_report_time = reminders.dinner_time
                reminders.enabled = True
            except ValueError:
                await message.answer("Формат времени: Напоминания 07:00 11:00 17:00")
                return
        else:
            await message.answer(
                _format_reminders_settings(reminders),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return
        await session.commit()
        await session.refresh(user)
        await session.refresh(reminders)

    if scheduler:
        schedule_user_reminders(scheduler, bot, user, reminders)
    await message.answer(
        _format_reminders_settings(reminders),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


def _format_reminders_settings(reminders: ReminderSettings) -> str:
    status = "включены" if reminders.enabled else "выключены"
    return (
        "Напоминания\n\n"
        f"Статус: {status}\n"
        f"Время: {reminders.breakfast_time:%H:%M}, {reminders.lunch_time:%H:%M}, {reminders.dinner_time:%H:%M}\n\n"
        "Изменить:\n"
        "<code>Напоминания 08:00 13:00 19:00</code>\n\n"
        "Выключить:\n"
        "<code>Напоминания выкл</code>\n\n"
        "Включить:\n"
        "<code>Напоминания вкл</code>"
    )


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    await message.answer(
        "Выгрузка JSON в чат отключена. Для отчётов используй кнопки Сегодня, Неделя, Месяц или Год.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.photo)
async def handle_photo_safe(message: Message, bot: Bot) -> None:
    if message.from_user.id in pending_support_users:
        pending_support_users.discard(message.from_user.id)
        await _send_support_message(message, bot)
        return

    await _react_food_logged(message)
    await message.answer("Фото получил, считаю...", reply_markup=main_menu_keyboard())

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        stream = await bot.download_file(file.file_path)
        image_bytes = stream.read()
        analysis = await asyncio.wait_for(analyze_food_image(image_bytes, message.caption), timeout=60)
    except Exception:
        logger.exception("Photo analysis failed")
        await message.answer(
            "Фото получил, но анализ сейчас не сработал. Напиши продукты и граммы текстом, я запишу обычным расчетом.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if analysis is None:
        await message.answer(
            "Фото получил, но GPT-анализ сейчас не работает. Пока напиши продукты и граммы текстом.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not analysis.items and analysis.total_calories <= 0:
        await message.answer(
            "Фото посмотрел, но не смог надежно оценить еду. Напиши продукты и граммы текстом.",
            reply_markup=main_menu_keyboard(),
        )
        return

    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        meal_log = await _create_photo_meal_log(session, user, analysis, photo.file_id)
        response_text = await _format_photo_meal_response(session, user, meal_log, prefix="Записал по фото")

    pending_photo_corrections[message.from_user.id] = PendingPhotoCorrection(
        meal_log_id=meal_log.id,
        image_bytes=image_bytes,
        expires_at=_photo_correction_deadline(),
        caption=message.caption,
    )
    await message.answer(response_text, reply_markup=main_menu_keyboard())


def _standard_meal_payload_from_text(text: str) -> str | None:
    lowered = text.lower().strip()
    for prefix in ("добавь шаблон ", "добавить шаблон ", "шаблон "):
        if lowered.startswith(prefix):
            return text.strip()[len(prefix) :].strip()
    return None


def _looks_like_standard_meal_definition(text: str) -> bool:
    parsed = _split_standard_meal_payload(text)
    if parsed is None:
        return False
    name, _ingredients = parsed
    return bool(re.fullmatch(r"(завтрак|обед|ужин|перекус)\s+\d+", name, re.IGNORECASE))


def _extract_explicit_calories(text: str) -> float | None:
    match = re.search(r"\b(\d{2,4}(?:[,.]\d+)?)\s*(?:ккал|кал(?:\.|орий|ории)?)\b", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 20 <= value <= 5000 else None


def _looks_like_explicit_food_calorie_entry(text: str) -> bool:
    lowered = text.lower()
    if _extract_explicit_calories(lowered) is None:
        return False
    daily_words = ("сколько", "осталось", "за день", "можно", "почему", "калораж", "посчитай")
    return not any(word in lowered for word in daily_words)


def _looks_like_targets_numbers(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"\s*\d{3,4}(?:[,.]\d+)?\s+\d{1,3}(?:[,.]\d+)?\s+\d{1,3}(?:[,.]\d+)?\s+\d{1,3}(?:[,.]\d+)?\s*",
            text,
        )
    )


def _is_target_accept(text: str) -> bool:
    lowered = text.lower().replace("ё", "е").strip(" .,!?\n\t")
    return lowered in {"да", "ок", "окей", "согласна", "согласен", "применить", "подтвердить", "хорошо"}


def _is_target_decline(text: str) -> bool:
    lowered = text.lower().replace("ё", "е").strip(" .,!?\n\t")
    return lowered in {"нет", "не надо", "отмена", "оставь", "оставить", "не менять"}


async def _update_own_targets_from_numbers(message: Message, text: str) -> None:
    parsed_targets, error = _parse_target_numbers(text.split())
    if error:
        await message.answer(_targets_help_text(error), parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    assert parsed_targets is not None
    calories, protein, fat, carbs = parsed_targets
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        await _apply_target_values(session, user, calories, protein, fat, carbs)
    await message.answer(
        f"Дневная норма обновлена: {calories:.0f} ккал, Б {protein:.0f}, Ж {fat:.0f}, У {carbs:.0f}.",
        reply_markup=main_menu_keyboard(),
    )


def _settings_payload_from_text(text: str) -> str | None:
    stripped = text.strip()
    lowered = stripped.lower().replace("ё", "е")
    if lowered in {"настройки", "профиль"}:
        return ""
    if lowered in {"вес", "мой вес", "настройки веса"}:
        return "вес"
    if any(lowered.startswith(prefix.replace("ё", "е")) for prefix in SETTINGS_FIELD_PREFIXES):
        return stripped
    for prefix in ("настройки ", "профиль "):
        if lowered.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return None


def _looks_like_standard_meal_definition(text: str) -> bool:
    parsed = _split_standard_meal_payload(text)
    if parsed is None:
        return False
    name, _ingredients = parsed
    return bool(re.fullmatch(r"(завтрак|обед|ужин|перекус)(?:\s+\d+)?", fix_text(name), re.IGNORECASE))


async def _handle_global_menu_text(
    message: Message,
    bot: Bot,
    scheduler: AsyncIOScheduler | None,
    lowered: str,
) -> bool:
    normalized = lowered.strip().replace("ё", "е")

    async def run(action) -> bool:
        _clear_pending_input_states(message.from_user.id)
        await action()
        return True

    if normalized in {"меню", "показать меню", "назад", "главное меню"}:
        return await run(lambda: cmd_menu(message))
    if normalized in {"период", "периоды", "отчеты", "отчёты"}:
        _clear_pending_input_states(message.from_user.id)
        await message.answer(PERIOD_MENU_TEXT, reply_markup=period_menu_keyboard())
        return True
    if normalized in {"сегодня", "итог дня", "калории за день", "калораж за день"}:
        return await run(lambda: cmd_today(message))
    if normalized in {"неделя", "итог недели"}:
        return await run(lambda: cmd_week(message))
    if normalized in {"месяц", "за месяц", "итог месяца", "месячный отчет", "отчет за месяц"}:
        return await run(lambda: cmd_month(message))
    if normalized in {"год", "за год", "итог года", "годовой отчет", "отчет за год"}:
        return await run(lambda: cmd_year(message))
    if normalized in {
        "за все время",
        "все время",
        "весь период",
        "за весь период",
        "итог за все время",
    }:
        return await run(lambda: cmd_all_time(message))
    if normalized in {"настройки"}:
        _clear_pending_input_states(message.from_user.id)
        await _answer_settings_menu(message)
        return True
    if normalized in {"профиль", "вес и цель"}:
        _clear_pending_input_states(message.from_user.id)
        await _answer_settings_menu(message)
        return True
    settings_field = _settings_field_from_button(normalized)
    if settings_field is not None:
        _clear_pending_input_states(message.from_user.id)
        await _start_settings_field_input(message, settings_field)
        return True
    if normalized == "дневная норма":
        return await run(lambda: _answer_daily_norm_settings(message))
    if normalized in {"лимиты кбжу", "лимиты", "цели кбжу", "кбжу"}:
        return await run(lambda: _answer_targets_settings(message))
    if normalized == "напоминания" or normalized.startswith("напоминания "):
        return await run(lambda: cmd_reminders(message, bot, scheduler))
    if normalized in {"шаги", "activity"}:
        return await run(lambda: cmd_activity(message))
    if normalized in {"совет", "рекомендация", "что съесть"}:
        return await run(lambda: _answer_recommendation(message))
    if normalized in {"вопрос", "задать вопрос"}:
        _clear_pending_input_states(message.from_user.id)
        await message.answer("Напиши вопрос обычным сообщением. Я отвечу по дневнику и целям.", reply_markup=main_menu_keyboard())
        return True
    if normalized in {"шаблоны", "мои блюда"}:
        return await run(lambda: cmd_list_meals(message))
    if normalized in {"помощь"}:
        _clear_pending_input_states(message.from_user.id)
        await message.answer(HELP_MENU_TEXT, reply_markup=help_menu_keyboard())
        return True
    if normalized in {"help"}:
        return await run(lambda: cmd_help(message))
    if normalized in {"изменить", "исправить", "поменять"}:
        return await run(lambda: _start_change_mode(message))
    if normalized in {"отменить", "отменить запись", "удалить запись", "убрать запись", "удалить прием"}:
        return await run(
            lambda: _start_change_mode(
                message,
                "Напиши, что нужно изменить в записи. Например: «убери хлеб из последнего обеда» или «замени калорийность последней записи на 650 ккал».",
            )
        )
    return False


@router.message(F.text)
async def handle_text(message: Message, bot: Bot, scheduler: AsyncIOScheduler | None = None) -> None:
    text = message.text.strip()
    lowered = text.lower()

    if _is_support_request(lowered):
        await cmd_support(message)
        return

    if message.from_user.id in pending_support_users:
        pending_support_users.discard(message.from_user.id)
        if lowered.strip().replace("ё", "е") in {"назад", "меню", "главное меню", "cancel", "не надо"}:
            await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
            return
        await _send_support_message(message, bot)
        return

    pending_target = pending_target_proposals.get(message.from_user.id)
    if pending_target is not None:
        if _is_target_accept(text):
            pending_target_proposals.pop(message.from_user.id, None)
            await _apply_pending_target_proposal(message, pending_target)
            return
        if _is_target_decline(text):
            pending_target_proposals.pop(message.from_user.id, None)
            await message.answer("Оставил текущую дневную норму без изменений.", reply_markup=main_menu_keyboard())
            return
        if _looks_like_targets_numbers(text):
            pending_target_proposals.pop(message.from_user.id, None)
            await _update_own_targets_from_numbers(message, text)
            return
        pending_target_proposals.pop(message.from_user.id, None)

    pending_settings_field = pending_settings_field_users.get(message.from_user.id)
    if pending_settings_field is not None:
        await _handle_settings_field_input(message, text, pending_settings_field)
        return

    if await _handle_global_menu_text(message, bot, scheduler, lowered):
        return

    if message.from_user.id in pending_weight_users:
        weight = _parse_weight_value(text)
        if weight is None:
            await message.answer("Не понял вес. Напиши одним числом, например: 107 или 107.4")
            return
        pending_weight_users.discard(message.from_user.id)
        await _save_weight(message, weight)
        return

    if message.from_user.id in pending_settings_users and (
        lowered in {"позже", "пропустить", "skip"} or _settings_payload_from_text(text) is not None
    ):
        if lowered in {"позже", "пропустить", "skip"}:
            pending_settings_users.discard(message.from_user.id)
            await message.answer(
                "Хорошо, настроим позже через /settings.",
                reply_markup=main_menu_keyboard(),
            )
            return

        settings_payload = _settings_payload_from_text(text)
        if settings_payload is not None:
            text = settings_payload

        async with async_session_maker() as session:
            user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
            error = await _update_settings_profile(session, user, text)
            latest_weight = await _latest_weight_log(session, user)
            missing = _missing_settings_fields(user, latest_weight) if not error else []
        if error:
            await message.answer(
                f"{error}\n\nМожно так: <code>Рост 170</code>, <code>Пол женский</code> или <code>Активность низкая</code>.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        if missing:
            await message.answer(
                _missing_settings_hint(missing),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        pending_settings_users.discard(message.from_user.id)
        async with async_session_maker() as session:
            user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
            latest_weight = await _latest_weight_log(session, user)
            proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight)
        if proposal is not None:
            await message.answer(
                _format_auto_targets_response("Профиль сохранён.", proposal),
                reply_markup=main_menu_keyboard(),
            )
            return
        await _answer_settings(message)
        return

    # Profile onboarding is optional. A food entry or any other ordinary text
    # must leave this mode and continue through the normal handlers below.
    pending_settings_users.discard(message.from_user.id)

    if message.from_user.id in pending_change_users:
        if lowered in {"не сейчас", "позже", "отмена", "отменить"}:
            pending_change_users.discard(message.from_user.id)
            await message.answer("Хорошо, ничего не меняю.", reply_markup=main_menu_keyboard())
            return
        pending_change_users.discard(message.from_user.id)
        await _apply_freeform_change(message, text)
        return

    if message.from_user.id in pending_standard_meal_users:
        if lowered in {"не сейчас", "позже", "отмена", "отменить"}:
            pending_standard_meal_users.discard(message.from_user.id)
            await message.answer("Хорошо, шаблон не добавляю.", reply_markup=main_menu_keyboard())
            return
        template_payload = _standard_meal_payload_from_text(text)
        if template_payload is None:
            await message.answer(
                "Чтобы сохранить шаблон, начни сообщение со слова «шаблон», например: шаблон обед салат 250 г, курица 120 г.",
                reply_markup=main_menu_keyboard(),
            )
            return
        saved = await _create_standard_meal_from_payload(message, template_payload)
        if saved:
            pending_standard_meal_users.discard(message.from_user.id)
        return

    pending_photo = _active_photo_correction(message.from_user.id)
    if pending_photo is not None and not text.startswith("/") and not _is_photo_control_text(lowered):
        await _handle_photo_correction(message, text, pending_photo)
        return

    if lowered in {"меню", "показать меню"}:
        await cmd_menu(message)
        return
    settings_payload = _settings_payload_from_text(text)
    if settings_payload is not None:
        await _answer_settings(message, settings_payload)
        return
    if _looks_like_targets_numbers(text):
        await _update_own_targets_from_numbers(message, text)
        return
    if lowered in {"записать вес"}:
        pending_weight_users.add(message.from_user.id)
        await message.answer("Напиши вес одним числом, например: 107 или 107.4", reply_markup=main_menu_keyboard())
        return
    if lowered in {"сегодня", "итог дня", "калории за день", "калораж за день"}:
        await cmd_today(message)
        return
    if lowered in {"неделя", "итог недели"}:
        await cmd_week(message)
        return
    if lowered in {"месяц", "за месяц", "итог месяца", "месячный отчет", "месячный отчёт", "отчет за месяц", "отчёт за месяц"}:
        await cmd_month(message)
        return
    if lowered in {"год", "за год", "итог года", "годовой отчет", "годовой отчёт", "отчет за год", "отчёт за год"}:
        await cmd_year(message)
        return
    if lowered in {
        "за все время",
        "за всё время",
        "все время",
        "всё время",
        "весь период",
        "за весь период",
        "итог за все время",
        "итог за всё время",
    }:
        await cmd_all_time(message)
        return
    if lowered == "напоминания" or lowered.startswith("напоминания "):
        await cmd_reminders(message, bot, scheduler)
        return
    if lowered in {"активность", "шаги", "activity"}:
        await cmd_activity(message)
        return
    if lowered in {"совет", "рекомендация", "что съесть"}:
        await _answer_recommendation(message)
        return
    if lowered in {"вопрос", "задать вопрос"}:
        await message.answer("Напиши вопрос обычным сообщением. Я отвечу по дневнику и целям.", reply_markup=main_menu_keyboard())
        return
    if lowered in {"шаблоны", "мои блюда"}:
        await cmd_list_meals(message)
        return
    if lowered in {"помощь", "help"}:
        await cmd_help(message)
        return
    if lowered in {"изменить", "исправить", "поменять"}:
        await _start_change_mode(message)
        return
    if lowered in {"отменить", "отменить запись", "удалить запись", "убрать запись", "удалить прием", "удалить приём"}:
        await _start_change_mode(
            message,
            "Напиши, что нужно изменить в записи. Например: «убери хлеб из последнего обеда» или «замени калорийность последней записи на 650 ккал».",
        )
        return

    template_payload = _standard_meal_payload_from_text(text)
    if template_payload is not None:
        await _create_standard_meal_from_payload(message, template_payload)
        return

    if _looks_like_confirmation(text):
        await message.answer("Понял как уточнение. Отдельной записью не считаю. Если надо поправить запись — нажми «Изменить».")
        return

    if _looks_like_daily_question(text):
        await _answer_daily_question(message)
        return

    if _looks_like_free_question(text):
        await _answer_free_question(message, text)
        return

    early_food_reaction = _looks_like_manual_food_entry_text(text)
    if early_food_reaction:
        await _react_food_logged(message)

    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        standard_meal = await find_standard_meal(session, user, text)
        if standard_meal:
            if not early_food_reaction:
                await _react_food_logged(message)
            meal_log = await log_standard_meal(session, user, standard_meal, standard_meal.name)
            await message.answer(await _format_meal_response(session, user, meal_log, prefix="Записал шаблон"))
            return

        dialog_decision = await interpret_dialog_message(session, user, text)
        if dialog_decision and await _handle_dialog_decision(
            message,
            session,
            user,
            dialog_decision,
            text,
            reaction_already_sent=early_food_reaction,
        ):
            return

        meal_log = await log_food_text(session, user, text)
        if meal_log:
            if not early_food_reaction:
                await _react_food_logged(message)
            await message.answer(await _format_meal_response(session, user, meal_log))
            return

    await message.answer("Не смог разобрать. Пример: «гречка 150 г, курица 120 г» или «обед 1».")


async def _handle_dialog_decision(
    message: Message,
    session,
    user: User,
    decision: DialogDecision,
    original_text: str,
    *,
    reaction_already_sent: bool = False,
) -> bool:
    action = decision.action

    if action == "show_today":
        report = await build_daily_report(session, user)
        await message.answer(format_daily_report(report), reply_markup=main_menu_keyboard())
        return True

    if action == "show_week":
        report = await build_weekly_report(session, user)
        await _answer_weekly_report(message, report)
        return True

    if action == "advice":
        recommendation = await recommend_next_meal(session, user)
        if decision.reply_text:
            recommendation = f"{decision.reply_text.strip()}\n\n{recommendation}"
        await message.answer(recommendation, reply_markup=main_menu_keyboard())
        return True

    if action == "log_weight" and decision.weight_kg is not None:
        session.add(WeightLog(user_id=user.id, date=date.today(), weight_kg=decision.weight_kg))
        await session.commit()
        await session.refresh(user)
        latest_weight = await _latest_weight_log(session, user)
        missing = _missing_settings_fields(user, latest_weight)
        if not missing:
            proposal = await _apply_recommended_targets_if_ready(session, user, latest_weight, skip_if_current=True)
            if proposal is not None:
                await message.answer(
                    _format_auto_targets_response(f"Вес записан: {decision.weight_kg:.1f} кг.", proposal),
                    reply_markup=main_menu_keyboard(),
                )
                return True
        await message.answer(f"Вес записан: {decision.weight_kg:.1f} кг.", reply_markup=main_menu_keyboard())
        return True

    if action == "log_food" and decision.food is not None:
        if not reaction_already_sent:
            await _react_food_logged(message)
        meal_log = await _create_dialog_meal_log(session, user, original_text, decision.food, "openai_text")
        await message.answer(await _format_meal_response(session, user, meal_log, prefix="Записал оценочно"))
        return True

    if action == "update_last_meal" and decision.food is not None:
        meal_log = await _latest_meal_log(session, user)
        if meal_log is None:
            if not reaction_already_sent:
                await _react_food_logged(message)
            meal_log = await _create_dialog_meal_log(session, user, original_text, decision.food, "openai_text")
            await message.answer(await _format_meal_response(session, user, meal_log, prefix="Записал оценочно"))
            return True
        _apply_dialog_estimate_to_log(meal_log, original_text, decision.food)
        await session.commit()
        await session.refresh(meal_log)
        await message.answer(await _format_meal_response(session, user, meal_log, prefix="Обновил оценочно"))
        return True

    if action == "answer":
        await message.answer(
            decision.reply_text.strip() or "Отвечу по дневнику: данных пока мало, но я вижу записи и цели.",
            reply_markup=main_menu_keyboard(),
        )
        return True

    if action == "clarify" and decision.confidence >= 0.7:
        await message.answer(
            decision.reply_text.strip() or "Уточни, пожалуйста, что именно нужно записать или посчитать.",
            reply_markup=main_menu_keyboard(),
        )
        return True

    return False


async def _apply_freeform_change(message: Message, change_text: str) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        meal_log = await _resolve_change_target_meal(session, user, change_text)
        if meal_log is None:
            if await _try_log_change_as_new_meal(message, session, user, change_text):
                return
            await message.answer(
                "За сегодня не нашёл подходящую запись для изменения. Если это новый приём пищи, отправь его обычным сообщением. Если это правка, напиши например: «в последнем обеде убрать хлеб 30 г».",
                reply_markup=main_menu_keyboard(),
            )
            return
        prompt = (
            "Это запрос на изменение уже существующей записи в дневнике, не новая еда. "
            "Пересчитай целиком именно эту изменяемую запись, учитывая правку пользователя. "
            f"Изменяемая запись: {meal_log.raw_user_input or meal_log.notes or meal_log.meal_type}; "
            f"сейчас {meal_log.calories:.0f} ккал, Б {meal_log.protein:.0f}, Ж {meal_log.fat:.0f}, У {meal_log.carbs:.0f}. "
            f"Правка пользователя: {change_text}"
        )
        decision = await interpret_dialog_message(session, user, prompt)
        if decision and decision.action in {"update_last_meal", "log_food"} and decision.food is not None:
            _apply_dialog_estimate_to_log(meal_log, change_text, decision.food)
            await session.commit()
            await session.refresh(meal_log)
            await message.answer(await _format_meal_response(session, user, meal_log, prefix="Обновил запись"))
            return
        if decision and decision.action in {"show_today", "show_week", "answer", "clarify"}:
            await message.answer(
                decision.reply_text.strip()
                or "Для правки напиши, что заменить в последней записи.",
                reply_markup=main_menu_keyboard(),
            )
            return
    await message.answer(
        "Не смог применить правку. Напиши конкретнее: что заменить и в какой записи, например «в последнем обеде хлеб 30 г убрать».",
        reply_markup=main_menu_keyboard(),
    )


def _today_bounds(user: User) -> tuple[datetime, datetime]:
    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    start = datetime.combine(today, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


async def _resolve_change_target_meal(session, user: User, change_text: str) -> MealLog | None:
    start, end = _today_bounds(user)
    result = await session.execute(
        select(MealLog)
        .where(MealLog.user_id == user.id, MealLog.datetime >= start, MealLog.datetime < end)
        .order_by(MealLog.datetime.desc())
    )
    logs = list(result.scalars().all())
    if not logs:
        return None

    lowered = fix_text(change_text).lower().replace("ё", "е")
    meal_aliases = {
        "завтрак": "breakfast",
        "обед": "lunch",
        "ужин": "dinner",
        "перекус": "snack",
    }
    for keyword, meal_type in meal_aliases.items():
        if keyword not in lowered:
            continue
        for log in logs:
            raw = fix_text(" ".join(part for part in (log.meal_type or "", log.raw_user_input or "", log.notes or "") if part)).lower().replace("ё", "е")
            if log.meal_type == meal_type or keyword in raw:
                return log
        return None

    if "фото" in lowered:
        for log in logs:
            if log.source_type == "photo_openai":
                return log
        return None

    return logs[0]


def _looks_like_new_food_from_change(text: str) -> bool:
    lowered = fix_text(text).lower().replace("ё", "е")
    if _looks_like_confirmation(text) or _looks_like_free_question(text):
        return False
    starts_as_meal = re.match(r"^\s*(?:завтрак|обед|ужин|перекус)\s*[:;,-]", lowered) is not None
    change_words = (
        "убрать",
        "убери",
        "замени",
        "заменить",
        "исправь",
        "исправить",
        "поменяй",
        "поменять",
        "добавь",
        "добавить",
        "в послед",
        "не ",
        "был",
        "была",
        "было",
    )
    if not starts_as_meal and any(word in lowered for word in change_words):
        return False
    if _extract_explicit_calories(lowered) is not None:
        return True
    if re.search(r"\b\d{1,4}(?:[,.]\d+)?\s*(?:г|гр|грамм|мл|шт|ккал|кал)\b", lowered):
        return True
    meal_words = ("завтрак", "обед", "ужин", "перекус")
    if any(lowered.startswith(word) for word in meal_words) and len(lowered.split()) >= 3:
        return True
    return False


def _looks_like_manual_food_entry_text(text: str) -> bool:
    lowered = fix_text(text).lower().replace("ё", "е").strip()
    if not lowered or lowered.startswith("/"):
        return False
    if _standard_meal_payload_from_text(text) is not None:
        return False
    if _extract_explicit_calories(lowered) is not None:
        return True
    if re.search(r"\b\d{1,4}(?:[,.]\d+)?\s*(?:г|гр|грамм|граммов|кг|мл|л|шт|штук)\b", lowered):
        return True
    if re.match(r"^\s*(?:завтрак|обед|ужин|перекус)\s*[:;,-]", lowered):
        return True
    return _contains_food_reaction_keyword(lowered)


def _contains_food_reaction_keyword(lowered_text: str) -> bool:
    return any(keyword in lowered_text for keyword in FOOD_REACTION_KEYWORDS)


async def _try_log_change_as_new_meal(message: Message, session, user: User, text: str) -> bool:
    if not _looks_like_new_food_from_change(text):
        return False

    await _react_food_logged(message)
    decision = await interpret_dialog_message(session, user, text)
    if decision and decision.food is not None:
        meal_log = await _create_dialog_meal_log(session, user, text, decision.food, "openai_text")
        await message.answer(await _format_meal_response(session, user, meal_log, prefix="Записал как новый приём"))
        return True

    meal_log = await log_food_text(session, user, text)
    if meal_log:
        await message.answer(await _format_meal_response(session, user, meal_log, prefix="Записал как новый приём"))
        return True
    return False


async def _create_dialog_meal_log(
    session,
    user: User,
    raw_user_input: str,
    estimate: DialogFoodEstimate,
    source_type: str,
) -> MealLog:
    meal_log = MealLog(
        user_id=user.id,
        datetime=datetime.now(ZoneInfo(user.timezone)),
        meal_type=estimate.meal_type or infer_meal_type(raw_user_input),
        source_type=source_type,
        raw_user_input=estimate.description or raw_user_input,
        calories=estimate.calories,
        protein=estimate.protein,
        fat=estimate.fat,
        carbs=estimate.carbs,
        fiber=estimate.fiber,
        micronutrients_json=_normalize_dialog_micros(estimate),
        confidence=estimate.confidence,
        notes=_dialog_estimate_notes(estimate),
    )
    session.add(meal_log)
    await session.commit()
    await session.refresh(meal_log)
    return meal_log


async def _latest_meal_log(session, user: User) -> MealLog | None:
    result = await session.execute(
        select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.datetime.desc()).limit(1)
    )
    return result.scalar_one_or_none()


def _apply_dialog_estimate_to_log(meal_log: MealLog, correction_text: str, estimate: DialogFoodEstimate) -> None:
    previous = meal_log.raw_user_input or meal_log.notes or ""
    meal_log.raw_user_input = estimate.description or f"{previous}; уточнение: {correction_text}"
    meal_log.meal_type = estimate.meal_type or meal_log.meal_type
    meal_log.calories = estimate.calories
    meal_log.protein = estimate.protein
    meal_log.fat = estimate.fat
    meal_log.carbs = estimate.carbs
    meal_log.fiber = estimate.fiber
    meal_log.micronutrients_json = _normalize_dialog_micros(estimate)
    meal_log.confidence = estimate.confidence
    meal_log.notes = _dialog_estimate_notes(estimate)


async def _create_photo_meal_log(
    session,
    user: User,
    analysis: FoodVisionAnalysis,
    photo_file_id: str | None = None,
) -> MealLog:
    meal_log = MealLog(
        user_id=user.id,
        datetime=datetime.now(ZoneInfo(user.timezone)),
        meal_type=analysis.meal_type or infer_meal_type(analysis.description),
        source_type="photo_openai",
        raw_user_input=analysis.description,
        photo_file_id=photo_file_id,
        calories=analysis.total_calories,
        protein=analysis.total_protein,
        fat=analysis.total_fat,
        carbs=analysis.total_carbs,
        fiber=analysis.total_fiber,
        micronutrients_json=_normalize_photo_micros(analysis),
        confidence=analysis.confidence,
        notes=_photo_analysis_notes(analysis),
    )
    session.add(meal_log)
    await session.commit()
    await session.refresh(meal_log)
    return meal_log


def _apply_photo_analysis_to_log(meal_log: MealLog, analysis: FoodVisionAnalysis, correction_text: str) -> None:
    meal_log.raw_user_input = analysis.description or f"{meal_log.raw_user_input}; уточнение: {correction_text}"
    meal_log.meal_type = analysis.meal_type or meal_log.meal_type
    meal_log.calories = analysis.total_calories
    meal_log.protein = analysis.total_protein
    meal_log.fat = analysis.total_fat
    meal_log.carbs = analysis.total_carbs
    meal_log.fiber = analysis.total_fiber
    meal_log.micronutrients_json = _normalize_photo_micros(analysis)
    meal_log.confidence = analysis.confidence
    meal_log.notes = _photo_analysis_notes(analysis)


def _photo_analysis_notes(analysis: FoodVisionAnalysis) -> str:
    if not analysis.items:
        return analysis.description
    return "\n".join(
        f"{item.name} {item.amount or f'{item.grams:.0f} г'} - {item.calories:.0f} ккал"
        for item in analysis.items
    )


def _normalize_photo_micros(analysis: FoodVisionAnalysis) -> dict[str, float]:
    return {key: 0.0 for key in MICRONUTRIENT_KEYS}


async def _format_photo_meal_response(
    session,
    user: User,
    meal_log: MealLog,
    prefix: str = "Записал по фото",
) -> str:
    report = await build_daily_report(session, user)
    items = meal_log.notes or meal_log.raw_user_input or "приём пищи"
    return (
        f"{prefix}:\n{items}\n\n"
        f"Этот приём: {meal_log.calories:.0f} ккал; "
        f"Б {meal_log.protein:.0f}, Ж {meal_log.fat:.0f}, У {meal_log.carbs:.0f}\n\n"
        f"{format_daily_summary(report)}"
    )


def _photo_correction_deadline() -> datetime:
    return datetime.now(ZoneInfo("UTC")) + PHOTO_CORRECTION_WINDOW


def _active_photo_correction(user_id: int) -> PendingPhotoCorrection | None:
    pending = pending_photo_corrections.get(user_id)
    if not pending:
        return None
    if pending.expires_at <= datetime.now(ZoneInfo("UTC")):
        pending_photo_corrections.pop(user_id, None)
        return None
    return pending


def _photo_correction_prompt(correction_text: str, pending: PendingPhotoCorrection) -> str:
    caption = f"\nИзначальная подпись к фото: {pending.caption}" if pending.caption else ""
    return (
        "Это уточнение к только что записанной фото-еде. "
        "Учти уточнение пользователя и пересчитай весь приём пищи целиком, "
        "средними значениями без диапазонов. "
        f"{caption}\nУточнение пользователя: {correction_text}"
    )


def _is_photo_control_text(lowered: str) -> bool:
    return lowered in {
        "меню",
        "показать меню",
        "сегодня",
        "итог дня",
        "калории за день",
        "калораж за день",
        "неделя",
        "итог недели",
        "месяц",
        "за месяц",
        "итог месяца",
        "месячный отчет",
        "месячный отчёт",
        "год",
        "за год",
        "итог года",
        "годовой отчет",
        "годовой отчёт",
        "за все время",
        "за всё время",
        "все время",
        "всё время",
        "весь период",
        "за весь период",
        "итог за все время",
        "итог за всё время",
        "напоминания",
        "шаблоны",
        "мои блюда",
        "помощь",
        "help",
        "поддержка",
        "написать в поддержку",
        "обратиться в поддержку",
        "support",
        "изменить",
        "исправить",
        "поменять",
    }


async def _handle_photo_correction(message: Message, text: str, pending: PendingPhotoCorrection) -> None:
    if _is_photo_confirmation(text):
        await message.answer(
            "Фото уже записано. Если нужно поправить, напиши уточнение словами в течение 5 минут.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if _is_photo_cancel(text):
        await message.answer(
            "Фото уже записано. Если нужно поправить состав или калорийность, нажми «Изменить» и напиши правку словами.",
            reply_markup=main_menu_keyboard(),
        )
        return

    prompt = _photo_correction_prompt(text, pending)
    analysis = await analyze_food_image(pending.image_bytes, prompt)
    if not analysis or (not analysis.items and analysis.total_calories <= 0):
        await message.answer(
            "Уточнение получил, но пересчёт по фото не сработал. Напиши продукты и граммы текстом.",
            reply_markup=main_menu_keyboard(),
        )
        return

    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        result = await session.execute(
            select(MealLog).where(MealLog.id == pending.meal_log_id, MealLog.user_id == user.id)
        )
        meal_log = result.scalar_one_or_none()
        if meal_log is None:
            pending_photo_corrections.pop(message.from_user.id, None)
            await message.answer("Не нашёл последнюю фото-запись для обновления.", reply_markup=main_menu_keyboard())
            return

        _apply_photo_analysis_to_log(meal_log, analysis, text)
        await session.commit()
        await session.refresh(meal_log)
        response_text = await _format_photo_meal_response(session, user, meal_log, prefix="Обновил по уточнению")

    pending_photo_corrections[message.from_user.id] = PendingPhotoCorrection(
        meal_log_id=pending.meal_log_id,
        image_bytes=pending.image_bytes,
        expires_at=_photo_correction_deadline(),
        caption=pending.caption,
    )
    await message.answer(response_text, reply_markup=main_menu_keyboard())


def _normalize_dialog_micros(estimate: DialogFoodEstimate) -> dict[str, float]:
    micros = estimate.micronutrients.model_dump() if estimate.micronutrients else {}
    return {key: float(micros.get(key, 0) or 0) for key in MICRONUTRIENT_KEYS}


def _dialog_estimate_notes(estimate: DialogFoodEstimate) -> str:
    if not estimate.items:
        return estimate.description
    items = ", ".join(f"{item.name} {item.amount}" for item in estimate.items)
    return f"{estimate.description}; {items}"


async def _format_meal_response(session, user: User, meal_log: MealLog, prefix: str = "Записал") -> str:
    report = await build_daily_report(session, user)
    name = _shorten_meal_name(meal_log.raw_user_input or meal_log.notes or "приём пищи")
    return (
        f"{prefix}: {name}\n"
        f"Этот приём: {meal_log.calories:.0f} ккал; "
        f"Б {meal_log.protein:.0f}, Ж {meal_log.fat:.0f}, У {meal_log.carbs:.0f}\n\n"
        f"{format_daily_summary(report)}"
    )

def _shorten_meal_name(value: str, limit: int = 160) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _is_photo_confirmation(text: str) -> bool:
    lowered = text.lower().replace("ё", "е").strip(" .,!?\n\t")
    return lowered in {
        "да",
        "да верно",
        "верно",
        "все верно",
        "все правильно",
        "правильно",
        "подтвердить",
        "подтверждаю",
        "записать",
        "запиши",
        "ок",
        "окей",
    }


def _is_photo_cancel(text: str) -> bool:
    lowered = text.lower().replace("ё", "е").strip(" .,!?\n\t")
    return lowered in {"отмена", "не записывать", "не надо", "отмени", "cancel", "stop"}


async def _answer_free_question(message: Message, question: str) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        answer = await answer_dietitian_question(session, user, question)
    await message.answer(answer, reply_markup=main_menu_keyboard())


async def _answer_recommendation(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        recommendation = await recommend_next_meal(session, user)
    await message.answer(recommendation, reply_markup=main_menu_keyboard())


def _looks_like_free_question(text: str) -> bool:
    lowered = text.lower().strip()
    question_words = (
        "?", "почему", "зачем", "как", "что", "когда", "можно ли", "можно",
        "лучше", "посоветуй", "совет", "план", "распредел", "объясни",
        "почему мало", "хочу похудеть", "что выбрать"
    )
    food_markers = (" г", " грам", "лож", "тарел", "порци", "шт")
    return any(word in lowered for word in question_words) and not any(marker in lowered for marker in food_markers)


def _looks_like_confirmation(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith(("да это", "и да", "всё верно", "все верно", "верно", "точно"))


def _looks_like_daily_question(text: str) -> bool:
    lowered = text.lower()
    if _looks_like_standard_meal_definition(text) or _looks_like_explicit_food_calorie_entry(text):
        return False
    question_words = ("сколько", "калори", "калораж", "можно съесть", "осталось", "за день", "похуд", "посчитай")
    return any(word in lowered for word in question_words) and not any(word in lowered for word in (" грамм", " лож"))


async def _answer_daily_question(message: Message) -> None:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.full_name)
        report = await build_daily_report(session, user)
    remaining = max(report.calories_target - report.calories_fact, 0)
    await message.answer(
        f"На сегодня записано: {report.calories_fact:.0f} ккал из цели {report.calories_target:.0f}.\n"
        f"Остаток: {remaining:.0f} ккал.\n"
        f"Белок: {report.protein_fact:.0f}/{report.protein_target:.0f} г, "
        f"жиры: {report.fat_fact:.0f}/{report.fat_target:.0f} г, "
        f"углеводы: {report.carbs_fact:.0f}/{report.carbs_target:.0f} г."
    )


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":", 1)
    return time(hour=int(hours), minute=int(minutes))
