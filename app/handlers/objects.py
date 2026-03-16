from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.db import Database
from app.keyboards import PAGE_SIZE, objects_list_kb, pager_kb


router = Router()


def _clamp_page(page: int) -> int:
    return max(0, page)


@router.message(lambda m: (m.text or "").strip() == "3. Объекты")
async def objects_entry(m: Message, db: Database) -> None:
    await _send_objects_page(m, db=db, page=0)


async def _send_objects_page(target: Message | CallbackQuery, *, db: Database, page: int) -> None:
    page = _clamp_page(page)
    total = await db.count_objects()
    offset = page * PAGE_SIZE
    objs = await db.list_objects(offset=offset, limit=PAGE_SIZE)

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    text = f"Объекты. Стр. {page+1}/{pages}\nВсего объектов: {total}\n\nВыберите объект:"

    items = [(o.id, o.name) for o in objs]
    has_prev = page > 0
    has_next = (page + 1) < pages
    kb = objects_list_kb(items, prefix="obj", page=page, has_prev=has_prev, has_next=has_next)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        if target.message:
            await target.message.edit_text(text, reply_markup=kb)
        await target.answer()


@router.callback_query(lambda c: (c.data or "").startswith("obj:page:"))
async def objects_page(c: CallbackQuery, db: Database) -> None:
    page = int((c.data or "obj:page:0").split(":")[2])
    await _send_objects_page(c, db=db, page=page)


@router.callback_query(lambda c: (c.data or "").startswith("obj:select:"))
async def object_select(c: CallbackQuery, db: Database) -> None:
    _, _, object_id_s, page_s = (c.data or "").split(":")
    object_id = int(object_id_s)
    page = int(page_s)

    obj = await db.get_object(object_id)
    if not obj:
        await c.answer("Объект не найден", show_alert=True)
        return

    # show tools on object
    offset = 0
    tools = await db.list_tools(
        offset=offset,
        limit=200,  # usually per object not huge; keep simple
        only_active=True,
        current_object_id=object_id,
        order_by="name",
    )
    lines = []
    for i, t in enumerate(tools, start=1):
        serial = t.serial or "—"
        lines.append(f"{i}) {t.name} — {serial}")

    body = "\n".join(lines) if lines else "На этом объекте инструмент пока не указан."
    hint = "\n\nЧтобы добавить/переместить инструмент на этот объект: откройте пункт 4 «Перемещение инструмента»."
    text = f"Объект: {obj.name}\n\n{body}{hint}"

    kb = pager_kb(prev_cb=None, next_cb=None, extra_buttons=[("↩️ К списку объектов", f"obj:page:{page}")])
    if c.message:
        await c.message.edit_text(text, reply_markup=kb)
    await c.answer()

