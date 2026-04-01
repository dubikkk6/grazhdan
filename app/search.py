from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db import Database
from app.states import SearchBySerialFlow


router = Router()


@router.message(lambda m: (m.text or "").strip() == "5. Поиск по инвентарному номеру")
async def search_entry(m: Message, state: FSMContext) -> None:
    await state.set_state(SearchBySerialFlow.serial)
    await m.answer(
        "Введите инвентарный номер (например 0001).\n"
        "Для отмены: /cancel"
    )


@router.message(SearchBySerialFlow.serial)
async def search_by_serial(m: Message, db: Database, state: FSMContext) -> None:
    serial = (m.text or "").strip()
    if not serial:
        await m.answer("Номер пустой. Введите инвентарный номер или /cancel.")
        return

    tool = await db.get_tool_by_serial(serial)
    if not tool:
        await m.answer(
            "Инструмент с таким номером не найден.\n"
            "Проверьте номер и попробуйте снова, или /cancel."
        )
        return

    if tool.current_object_id is None:
        object_name = "Без объекта"
    else:
        obj = await db.get_object(tool.current_object_id)
        object_name = obj.name if obj else "Объект не найден"

    status = "в работе" if tool.is_active else "списан"
    await state.clear()
    await m.answer(
        "Найдено:\n"
        f"- Инструмент: {tool.name}\n"
        f"- Номер: {tool.serial or '—'}\n"
        f"- Статус: {status}\n"
        f"- Текущий объект: {object_name}"
    )
