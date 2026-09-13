from app.config import Settings, get_settings


def parse_telegram_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()

    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        value = part.strip()
        if not value:
            continue
        try:
            ids.add(int(value))
        except ValueError:
            continue
    return ids


def allowed_telegram_ids(settings: Settings | None = None) -> set[int]:
    settings = settings or get_settings()
    ids = parse_telegram_ids(settings.telegram_allowed_ids)
    if settings.telegram_admin_id is not None:
        ids.add(settings.telegram_admin_id)
    return ids


def is_admin(telegram_id: int | None, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return telegram_id is not None and settings.telegram_admin_id == telegram_id


def is_allowed_telegram_user(telegram_id: int | None, settings: Settings | None = None) -> bool:
    if telegram_id is None:
        return False

    ids = allowed_telegram_ids(settings)
    return telegram_id in ids
