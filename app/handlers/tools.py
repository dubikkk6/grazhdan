from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.db import Database
from app.keyboards import PAGE_SIZE, pager_kb


router = Router()


def _clamp_page(page: int) -> int:
    return max(0, page)


async def _render_tools_page(db: Database, *, page: int) -> tuple[str, int]:
    page = _clamp_page(page)
    total = await db.count_tools(only_active=True)
    offset = page * PAGE_SIZE
    tools = await db.list_tools(offset=offset, limit=PAGE_SIZE, only_active=True, order_by="name")
    lines = []
    for i, t in enumerate(tools, start=offset + 1):
        lines.append(f"{i}. {t.name}")
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    header = f"Список инструмента (активный). Стр. {page+1}/{pages}\nВсего: {total}\n"
    body = "\n".join(lines) if lines else "Пока нет инструментов."
    return header + "\n" + body, total


@router.message(lambda m: (m.text or "").strip() == "1. Список инструментов")
async def tools_list(m: Message, db: Database) -> None:
    text, total = await _render_tools_page(db, page=0)
    has_next = total > PAGE_SIZE
    kb = pager_kb(prev_cb=None, next_cb="tools:page:1" if has_next else None)
    await m.answer(text, reply_markup=kb)


@router.callback_query(lambda c: (c.data or "").startswith("tools:page:"))
async def tools_page(c: CallbackQuery, db: Database) -> None:
    page = int((c.data or "tools:page:0").split(":")[2])
    text, total = await _render_tools_page(db, page=page)
    page = _clamp_page(page)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    has_prev = page > 0
    has_next = (page + 1) < pages
    kb = pager_kb(
        prev_cb=f"tools:page:{page-1}" if has_prev else None,
        next_cb=f"tools:page:{page+1}" if has_next else None,
    )
    if c.message:
        await c.message.edit_text(text, reply_markup=kb)
    await c.answer()


async def _render_tools_num_page(db: Database, *, page: int) -> tuple[str, int]:
    page = _clamp_page(page)
    total = await db.count_tools(with_serial=True, only_active=True)
    offset = page * PAGE_SIZE
    tools = await db.list_tools(
        offset=offset, limit=PAGE_SIZE, with_serial=True, only_active=True, order_by="serial"
    )
    lines = []
    for i, t in enumerate(tools, start=offset + 1):
        serial = t.serial or "—"
        lines.append(f"{i}. {t.name} — {serial}")
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    header = f"Инструменты + номер. Стр. {page+1}/{pages}\nВсего: {total}\n"
    body = "\n".join(lines) if lines else "Пока нет инструментов с номером."
    return header + "\n" + body, total


@router.message(lambda m: (m.text or "").strip() == "2. Инструменты + номер")
async def tools_num_list(m: Message, db: Database) -> None:
    text, total = await _render_tools_num_page(db, page=0)
    has_next = total > PAGE_SIZE
    kb = pager_kb(prev_cb=None, next_cb="toolsnum:page:1" if has_next else None)
    await m.answer(text, reply_markup=kb)


@router.callback_query(lambda c: (c.data or "").startswith("toolsnum:page:"))
async def tools_num_page(c: CallbackQuery, db: Database) -> None:
    page = int((c.data or "toolsnum:page:0").split(":")[2])
    text, total = await _render_tools_num_page(db, page=page)
    page = _clamp_page(page)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    has_prev = page > 0
    has_next = (page + 1) < pages
    kb = pager_kb(
        prev_cb=f"toolsnum:page:{page-1}" if has_prev else None,
        next_cb=f"toolsnum:page:{page+1}" if has_next else None,
    )
    if c.message:
        await c.message.edit_text(text, reply_markup=kb)
    await c.answer()

