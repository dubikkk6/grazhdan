from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


PAGE_SIZE = 20


def main_menu_kb(is_admin: bool) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="1. Список инструментов"))
    b.row(KeyboardButton(text="2. Инструменты + номер"))
    b.row(KeyboardButton(text="3. Объекты"))
    b.row(KeyboardButton(text="4. Перемещение инструмента"))
    return b.as_markup(resize_keyboard=True, selective=True)


def pager_kb(*, prev_cb: str | None, next_cb: str | None, extra_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if prev_cb:
        b.button(text="⬅️ Назад", callback_data=prev_cb)
    if next_cb:
        b.button(text="Вперёд ➡️", callback_data=next_cb)
    if prev_cb or next_cb:
        b.adjust(2)
    if extra_buttons:
        for text, cb in extra_buttons:
            b.button(text=text, callback_data=cb)
        b.adjust(1)
    return b.as_markup()


def objects_list_kb(items: list[tuple[int, str]], *, prefix: str, page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for object_id, name in items:
        b.button(text=name, callback_data=f"{prefix}:select:{object_id}:{page}")
    b.adjust(1)
    prev_cb = f"{prefix}:page:{page-1}" if has_prev else None
    next_cb = f"{prefix}:page:{page+1}" if has_next else None
    if prev_cb or next_cb:
        b.row()
        if prev_cb:
            b.button(text="⬅️", callback_data=prev_cb)
        if next_cb:
            b.button(text="➡️", callback_data=next_cb)
        b.adjust(1, 2)
    return b.as_markup()


def tools_pick_kb(items: list[tuple[int, str]], *, prefix: str, page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tool_id, label in items:
        b.button(text=label, callback_data=f"{prefix}:pick:{tool_id}:{page}")
    b.adjust(1)
    prev_cb = f"{prefix}:page:{page-1}" if has_prev else None
    next_cb = f"{prefix}:page:{page+1}" if has_next else None
    if prev_cb or next_cb:
        b.row()
        if prev_cb:
            b.button(text="⬅️", callback_data=prev_cb)
        if next_cb:
            b.button(text="➡️", callback_data=next_cb)
        b.adjust(1, 2)
    return b.as_markup()

