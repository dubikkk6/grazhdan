from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Settings
from app.db import Database
from app.keyboards import main_menu_kb
from app.texts import HELP_TEXT


router = Router()


@router.message(CommandStart())
async def start(m: Message, db: Database, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    tg_id = m.from_user.id if m.from_user else 0
    is_admin = tg_id in settings.admin_ids
    await db.upsert_user(
        tg_id=tg_id,
        full_name=m.from_user.full_name if m.from_user else None,
        username=m.from_user.username if m.from_user else None,
        is_admin=is_admin,
    )
    await m.answer(
        "Меню инвентаризации инструмента. Выберите пункт:",
        reply_markup=main_menu_kb(is_admin=is_admin),
    )


@router.message(Command("help"))
async def help_cmd(m: Message) -> None:
    await m.answer(HELP_TEXT)

