from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import load_settings
from app.db import Database
from app.handlers import admin, menu, move, objects, search, tools
from app.middlewares import InjectMiddleware



async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    settings = load_settings()
    db = Database(settings.db_path)
    await db.init()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(InjectMiddleware(db=db, settings=settings))

    dp.include_router(menu.router)
    dp.include_router(tools.router)
    dp.include_router(objects.router)
    dp.include_router(move.router)
    dp.include_router(search.router)
    dp.include_router(admin.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

