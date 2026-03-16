from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Database
from app.keyboards import PAGE_SIZE, objects_list_kb, tools_pick_kb
from app.states import MoveToolFlow


router = Router()


def _clamp_page(page: int) -> int:
    return max(0, page)


def _confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="move:confirm")
    b.button(text="❌ Отмена", callback_data="move:cancel")
    b.adjust(2)
    return b.as_markup()


@router.message(lambda m: (m.text or "").strip() == "4. Перемещение инструмента")
async def move_entry(m: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(MoveToolFlow.from_object_id)
    await m.answer("Подсказка: чтобы *добавить инструмент на объект впервые*, выберите «— Без объекта —» как место, откуда забрали.")
    await _send_from_objects(m, db=db, page=0)


async def _send_from_objects(target: Message | CallbackQuery, *, db: Database, page: int) -> None:
    page = _clamp_page(page)
    objects_count = await db.count_objects()
    total = objects_count + 1  # + "Без объекта"
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # build list with "Без объекта" (virtual object_id = -1) only on page 0
    if page == 0:
        objs = await db.list_objects(offset=0, limit=max(0, PAGE_SIZE - 1))
        items: list[tuple[int, str]] = [(-1, "— Без объекта —")] + [(o.id, o.name) for o in objs]
    else:
        # page 0 uses 1 slot for "Без объекта", so shift offsets by -1
        offset = page * PAGE_SIZE - 1
        objs = await db.list_objects(offset=offset, limit=PAGE_SIZE)
        items = [(o.id, o.name) for o in objs]

    has_prev = page > 0
    has_next = (page + 1) < pages
    kb = objects_list_kb(items, prefix="movefrom", page=page, has_prev=has_prev, has_next=has_next)

    text = "Откуда забрали инструмент? Выберите объект:"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        if target.message:
            await target.message.edit_text(text, reply_markup=kb)
        await target.answer()


@router.callback_query(lambda c: (c.data or "").startswith("movefrom:page:"))
async def move_from_page(c: CallbackQuery, db: Database) -> None:
    page = int((c.data or "movefrom:page:0").split(":")[2])
    await _send_from_objects(c, db=db, page=page)


@router.callback_query(lambda c: (c.data or "").startswith("movefrom:select:"))
async def move_from_select(c: CallbackQuery, db: Database, state: FSMContext) -> None:
    _, _, object_id_s, page_s = (c.data or "").split(":")
    object_id = int(object_id_s)
    page = int(page_s)
    await state.update_data(from_object_id=object_id, from_page=page)
    await state.set_state(MoveToolFlow.tool_id)
    await _send_tools_on_object(c, db=db, object_id=object_id, page=0)


async def _send_tools_on_object(target: Message | CallbackQuery, *, db: Database, object_id: int, page: int) -> None:
    page = _clamp_page(page)
    total = await db.count_tools(only_active=True, current_object_id=object_id)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    offset = page * PAGE_SIZE
    tools = await db.list_tools(
        offset=offset,
        limit=PAGE_SIZE,
        only_active=True,
        current_object_id=object_id,
        order_by="name",
    )
    items = [(t.id, f"{t.name} — {t.serial or '—'}") for t in tools]
    has_prev = page > 0
    has_next = (page + 1) < pages
    kb = tools_pick_kb(items, prefix=f"movetool:{object_id}", page=page, has_prev=has_prev, has_next=has_next)

    obj = None if object_id == -1 else await db.get_object(object_id)
    obj_name = "Без объекта" if object_id == -1 else (obj.name if obj else "—")
    text = f"Выберите инструмент (откуда: {obj_name}):"

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        if target.message:
            await target.message.edit_text(text, reply_markup=kb)
        await target.answer()


@router.callback_query(lambda c: (c.data or "").startswith("movetool:"))
async def move_tool_callbacks(c: CallbackQuery, db: Database, state: FSMContext) -> None:
    parts = (c.data or "").split(":")
    # formats:
    # movetool:<from_object_id>:page:<n>
    # movetool:<from_object_id>:pick:<tool_id>:<page>
    if len(parts) < 4:
        await c.answer()
        return

    from_object_id = int(parts[1])
    action = parts[2]

    if action == "page":
        page = int(parts[3])
        await _send_tools_on_object(c, db=db, object_id=from_object_id, page=page)
        return

    if action == "pick":
        tool_id = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 0
        await state.update_data(tool_id=tool_id, tool_page=page)
        await state.set_state(MoveToolFlow.to_object_id)
        await _send_to_objects(c, db=db, page=0)
        return

    await c.answer()


async def _send_to_objects(target: Message | CallbackQuery, *, db: Database, page: int) -> None:
    page = _clamp_page(page)
    total = await db.count_objects()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    offset = page * PAGE_SIZE
    objs = await db.list_objects(offset=offset, limit=PAGE_SIZE)
    items = [(o.id, o.name) for o in objs]
    has_prev = page > 0
    has_next = (page + 1) < pages
    kb = objects_list_kb(items, prefix="moveto", page=page, has_prev=has_prev, has_next=has_next)
    text = "Куда переместили инструмент? Выберите объект:"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        if target.message:
            await target.message.edit_text(text, reply_markup=kb)
        await target.answer()


@router.callback_query(lambda c: (c.data or "").startswith("moveto:page:"))
async def move_to_page(c: CallbackQuery, db: Database) -> None:
    page = int((c.data or "moveto:page:0").split(":")[2])
    await _send_to_objects(c, db=db, page=page)


@router.callback_query(lambda c: (c.data or "").startswith("moveto:select:"))
async def move_to_select(c: CallbackQuery, db: Database, state: FSMContext) -> None:
    _, _, object_id_s, page_s = (c.data or "").split(":")
    to_object_id = int(object_id_s)
    await state.update_data(to_object_id=to_object_id, to_page=int(page_s))
    await state.set_state(MoveToolFlow.confirm)

    data = await state.get_data()
    tool = await db.get_tool_by_id(int(data["tool_id"]))
    to_obj = await db.get_object(to_object_id)
    from_id = int(data.get("from_object_id", -1))
    from_obj = None if from_id == -1 else await db.get_object(from_id)
    from_name = "Без объекта" if from_id == -1 else (from_obj.name if from_obj else "—")

    text = (
        "Подтвердите перемещение:\n\n"
        f"- Инструмент: {(tool.name if tool else '—')} — {(tool.serial if tool and tool.serial else '—')}\n"
        f"- Откуда: {from_name}\n"
        f"- Куда: {to_obj.name if to_obj else '—'}"
    )
    if c.message:
        await c.message.edit_text(text, reply_markup=_confirm_kb())
    await c.answer()


@router.callback_query(lambda c: (c.data or "") in {"move:confirm", "move:cancel"})
async def move_confirm_cancel(c: CallbackQuery, db: Database, state: FSMContext) -> None:
    if (c.data or "") == "move:cancel":
        await state.clear()
        if c.message:
            await c.message.edit_text("Операция отменена.")
        await c.answer()
        return

    data = await state.get_data()
    tool_id = int(data["tool_id"])
    to_object_id = int(data["to_object_id"])
    moved_by = c.from_user.id if c.from_user else 0
    await db.move_tool(tool_id=tool_id, to_object_id=to_object_id, moved_by_tg_id=moved_by)
    await state.clear()
    if c.message:
        await c.message.edit_text("Готово. Инструмент перемещён и записан в журнал.")
    await c.answer()


@router.message(lambda m: (m.text or "").strip().lower() in {"/cancel", "отмена"})
async def cancel_any(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer("Операция отменена.")

