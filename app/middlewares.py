from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import Settings
from app.db import Database


class InjectMiddleware(BaseMiddleware):
    def __init__(self, *, db: Database, settings: Settings):
        super().__init__()
        self._db = db
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["db"] = self._db
        data["settings"] = self._settings
        return await handler(event, data)

