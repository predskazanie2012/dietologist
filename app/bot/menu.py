from aiogram.types import BotCommand, KeyboardButton, ReplyKeyboardMarkup


MAIN_MENU_TEXT = "Выбери раздел или просто напиши еду."
PERIOD_MENU_TEXT = "Выбери отчёт."
SETTINGS_MENU_TEXT = "Что изменить?"
HELP_MENU_TEXT = "Что нужно сделать?"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отчеты"), KeyboardButton(text="Настройки")],
            [KeyboardButton(text="Шаблоны"), KeyboardButton(text="Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Напиши еду, отправь фото или выбери действие",
    )


def period_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сегодня"), KeyboardButton(text="Неделя")],
            [KeyboardButton(text="Месяц"), KeyboardButton(text="Год")],
            [KeyboardButton(text="За все время"), KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери отчёт",
    )


def settings_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Вес"), KeyboardButton(text="Желаемый вес")],
            [KeyboardButton(text="Рост"), KeyboardButton(text="Возраст")],
            [KeyboardButton(text="Пол"), KeyboardButton(text="Активность")],
            [KeyboardButton(text="Дневная норма"), KeyboardButton(text="Лимиты КБЖУ")],
            [KeyboardButton(text="Напоминания"), KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери настройку",
    )


def sex_settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Женский"), KeyboardButton(text="Мужской")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери пол",
    )


def activity_settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Низкая"), KeyboardButton(text="Лёгкая")],
            [KeyboardButton(text="Средняя"), KeyboardButton(text="Высокая")],
            [KeyboardButton(text="Очень высокая")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери активность",
    )


def help_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Изменить")],
            [KeyboardButton(text="Обратиться в поддержку")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие",
    )


def bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Открыть меню"),
    ]
