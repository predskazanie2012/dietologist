from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.services.access import is_allowed_telegram_user


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        telegram_id = event.from_user.id if event.from_user else None
        text_parts = (event.text or "").split(maxsplit=1)
        command = text_parts[0].lower().split("@", 1)[0] if text_parts else ""
        if command == "/whoami":
            return await handler(event, data)

        if not is_allowed_telegram_user(telegram_id):
            return None

        return await handler(event, data)
