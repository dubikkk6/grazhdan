from __future__ import annotations

import csv
import io

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import Settings
from app.db import Database
from app.states import (
    AdminAddObject,
    AdminAddTool,
    AdminDisposeTool,
    AdminImportObjects,
    AdminImportTools,
    AdminRestoreTool,
    AdminDeleteObject,
)


router = Router()


def _admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить инструмент", callback_data="admin:add_tool")
    b.button(text="📥 Импорт инструментов (текст)", callback_data="admin:import_tools")
    b.button(text="🗑️ Списать инструмент (по номеру)", callback_data="admin:dispose")
    b.button(text="♻️ Восстановить инструмент (по номеру)", callback_data="admin:restore")
    b.button(text="➕ Добавить объект", callback_data="admin:add_object")
    b.button(text="🗑️ Удалить объект", callback_data="admin:delete_object")  
    b.button(text="📥 Импорт объектов (текст)", callback_data="admin:import_objects")
    b.button(text="📤 Экспорт инструментов CSV", callback_data="admin:export_tools")
    b.adjust(1)
    return b.as_markup()


def _is_admin(tg_id: int, settings: Settings) -> bool:
    return tg_id in settings.admin_ids


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def show_objects_for_deletion(message: Message, db: Database, offset: int = 0):
    """Показывает список объектов для выбора удаления"""
    limit = 10
    objects = await db.list_objects(offset=offset, limit=limit)
    total = await db.count_objects()
    
    builder = InlineKeyboardBuilder()
    
    for obj in objects:
        builder.button(
            text=f"🗑️ {obj.name}",
            callback_data=f"admin:delete_obj:{obj.id}"
        )
    
    # Навигация
    if offset > 0:
        builder.button(text="◀️ Назад", callback_data=f"admin:delete_page:{offset - limit}")
    if offset + limit < total:
        builder.button(text="Вперед ▶️", callback_data=f"admin:delete_page:{offset + limit}")
    
    builder.button(text="🔙 Отмена", callback_data="admin:delete_cancel")
    builder.adjust(1)
    
    await message.edit_text(
        f"Выберите объект для удаления (всего объектов: {total}):\n\n"
        "⚠️ Внимание: объект можно удалить, только если на нём нет инструментов.",
        reply_markup=builder.as_markup()
    )


# ==================== КОМАНДА АДМИНКИ ====================

@router.message(Command("admin"))
async def admin_entry(m: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    tg_id = m.from_user.id if m.from_user else 0
    if not _is_admin(tg_id, settings):
        await m.answer("У вас нет доступа к админке.")
        return
    await m.answer("Админка: выберите действие.", reply_markup=_admin_menu_kb())


# ==================== ОБРАБОТЧИКИ CALLBACK ====================

@router.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def admin_callbacks(c: CallbackQuery, db: Database, settings: Settings, state: FSMContext) -> None:
    tg_id = c.from_user.id if c.from_user else 0
    if not _is_admin(tg_id, settings):
        await c.answer("Нет доступа", show_alert=True)
        return

    action_parts = c.data.split(":")
    action = action_parts[1]
    
    # ===== ДЕЙСТВИЯ С ИНСТРУМЕНТАМИ =====
    if action == "add_tool":
        await state.set_state(AdminAddTool.name)
        if c.message:
            await c.message.edit_text("Введите наименование инструмента:")
        await c.answer()
        return

    if action == "import_tools":
        await state.set_state(AdminImportTools.csv_text)
        if c.message:
            await c.message.edit_text(
                "Отправьте список инструментов текстом.\n\n"
                "Формат построчно, разделитель `;` (или `,`/таб):\n"
                "- `0001;Пила`\n"
                "- `Пила;0001`\n"
                "- `Пила` (если без номера)\n"
            )
        await c.answer()
        return

    if action == "dispose":
        await state.set_state(AdminDisposeTool.serial)
        if c.message:
            await c.message.edit_text("Введите номер инструмента (например 0001), который нужно списать:")
        await c.answer()
        return

    if action == "restore":
        await state.set_state(AdminRestoreTool.serial)
        if c.message:
            await c.message.edit_text("Введите номер инструмента (например 0001), который нужно восстановить:")
        await c.answer()
        return

    # ===== ДЕЙСТВИЯ С ОБЪЕКТАМИ =====
    if action == "add_object":
        await state.set_state(AdminAddObject.name)
        if c.message:
            await c.message.edit_text("Введите наименование объекта:")
        await c.answer()
        return

    if action == "import_objects":
        await state.set_state(AdminImportObjects.text)
        if c.message:
            await c.message.edit_text("Отправьте список объектов текстом (каждый объект с новой строки).")
        await c.answer()
        return

    if action == "delete_object":
        # Начало процесса удаления объекта
        await state.clear()
        total_objects = await db.count_objects()
        if total_objects == 0:
            await c.message.edit_text("В системе нет объектов для удаления.")
            await c.answer()
            return
        await show_objects_for_deletion(c.message, db, 0)
        await c.answer()
        return

    # ===== ПАГИНАЦИЯ ПРИ УДАЛЕНИИ =====
    if action == "delete_page":
        offset = int(action_parts[2])
        await show_objects_for_deletion(c.message, db, offset)
        await c.answer()
        return

    # ===== ВЫБОР ОБЪЕКТА ДЛЯ УДАЛЕНИЯ =====
    if action == "delete_obj":
        object_id = int(action_parts[2])
        obj = await db.get_object(object_id)
        
        if not obj:
            await c.message.edit_text("Объект не найден. Возможно, он уже был удалён.")
            await c.answer()
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(object_id=object_id, object_name=obj.name)
        await state.set_state(AdminDeleteObject.confirm)
        
        # Кнопки подтверждения
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, удалить", callback_data="admin:delete_confirm_yes")
        builder.button(text="❌ Нет, отмена", callback_data="admin:delete_confirm_no")
        builder.adjust(2)
        
        await c.message.edit_text(
            f"⚠️ Вы уверены, что хотите удалить объект **{obj.name}**?\n\n"
            "Это действие нельзя отменить. Объект будет удалён безвозвратно.",
            reply_markup=builder.as_markup()
        )
        await c.answer()
        return

    # ===== ОТМЕНА УДАЛЕНИЯ =====
    if action == "delete_cancel":
        await state.clear()
        await c.message.edit_text(
            "Удаление отменено. Выберите действие:",
            reply_markup=_admin_menu_kb()
        )
        await c.answer()
        return

    # ===== ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ =====
    if action == "delete_confirm_yes":
        # Проверяем состояние
        current_state = await state.get_state()
        if current_state != AdminDeleteObject.confirm:
            await c.answer("Ошибка: неверное состояние", show_alert=True)
            return
        
        data = await state.get_data()
        object_id = data.get("object_id")
        object_name = data.get("object_name", "Неизвестный объект")
        
        if not object_id:
            await c.message.edit_text("Ошибка: данные не найдены.")
            await state.clear()
            await c.answer()
            return
        
        # Пытаемся удалить объект
        success, message_text = await db.delete_object(object_id)
        
        if success:
            await c.message.edit_text(
                f"✅ Объект **{object_name}** удалён.\n\n_{message_text}_",
                reply_markup=_admin_menu_kb()
            )
        else:
            # Если не удалось удалить (есть инструменты)
            builder = InlineKeyboardBuilder()
            builder.button(text="🔍 Показать инструменты", callback_data=f"admin:show_tools:{object_id}")
            builder.button(text="◀️ Назад к списку", callback_data="admin:delete_object")
            builder.adjust(1)
            
            await c.message.edit_text(
                f"❌ Не удалось удалить объект **{object_name}**.\n\n_{message_text}_",
                reply_markup=builder.as_markup()
            )
        
        await state.clear()
        await c.answer()
        return

    if action == "delete_confirm_no":
        await state.clear()
        await c.message.edit_text(
            "Удаление отменено. Выберите действие:",
            reply_markup=_admin_menu_kb()
        )
        await c.answer()
        return

    # ===== ПОКАЗ ИНСТРУМЕНТОВ НА ОБЪЕКТЕ =====
    if action == "show_tools":
        object_id = int(action_parts[2])
        obj = await db.get_object(object_id)
        
        if not obj:
            await c.message.edit_text("Объект не найден.")
            await c.answer()
            return
        
        # Получаем инструменты на этом объекте
        tools = await db.list_tools(
            offset=0,
            limit=100,
            only_active=True,
            current_object_id=object_id
        )
        
        if not tools:
            await c.message.edit_text(
                f"На объекте **{obj.name}** нет инструментов.",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад к удалению", callback_data="admin:delete_object"
                ).as_markup()
            )
            await c.answer()
            return
        
        tools_text = "\n".join([
            f"• {t.name}" + (f" (номер: {t.serial})" if t.serial else "")
            for t in tools[:20]
        ])
        
        if len(tools) > 20:
            tools_text += f"\n... и ещё {len(tools) - 20} инструментов"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Переместить инструменты", callback_data="admin:move_tool")
        builder.button(text="◀️ Назад к удалению", callback_data="admin:delete_object")
        builder.adjust(1)
        
        await c.message.edit_text(
            f"📦 Инструменты на объекте **{obj.name}** (всего: {len(tools)}):\n\n{tools_text}\n\n"
            "Чтобы удалить объект, сначала переместите все инструменты с него.",
            reply_markup=builder.as_markup()
        )
        await c.answer()
        return

    # ===== ЭКСПОРТ =====
    if action == "export_tools":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["id", "name", "serial", "is_active", "object_name"])
        async for row in db.export_tools_rows():
            w.writerow(list(row))
        data = buf.getvalue().encode("utf-8-sig")
        file = BufferedInputFile(data, filename="tools_export.csv")
        if c.message:
            await c.message.answer_document(file, caption="Экспорт инструментов (CSV).")
        await c.answer("Готово")
        return

    await c.answer()


# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ (FSM) ====================

@router.message(AdminAddTool.name)
async def admin_add_tool_name(m: Message, state: FSMContext) -> None:
    name = (m.text or "").strip()
    if not name:
        await m.answer("Введите непустое наименование инструмента:")
        return
    await state.update_data(name=name)
    await state.set_state(AdminAddTool.serial)
    await m.answer("Введите номер (например 0001) или отправьте `-`, если номера нет:")


@router.message(AdminAddTool.serial)
async def admin_add_tool_serial(m: Message, db: Database, state: FSMContext) -> None:
    raw = (m.text or "").strip()
    serial = None if raw in {"-", "—", ""} else raw
    data = await state.get_data()
    name = str(data["name"])
    tool_id = await db.create_or_update_tool(name=name, serial=serial)
    await state.clear()
    await m.answer(
        f"Готово. Инструмент сохранён (id={tool_id}).\n"
        "Назначить инструмент на объект можно через пункт «Перемещение инструмента» (выберите «— Без объекта —»).",
        reply_markup=_admin_menu_kb(),
    )


def _split_cols(line: str) -> list[str]:
    for sep in (";", "\t", ","):
        if sep in line:
            return [c.strip() for c in line.split(sep)]
    return [line.strip()]


def _looks_like_serial(s: str) -> bool:
    s = s.strip()
    return s.isdigit() and 1 <= len(s) <= 12


@router.message(AdminImportTools.csv_text)
async def admin_import_tools_text(m: Message, db: Database, state: FSMContext) -> None:
    text = (m.text or "").strip()
    if not text:
        await m.answer("Пусто. Пришлите текст со списком.")
        return

    created = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cols = [c for c in _split_cols(line) if c]
        name: str | None = None
        serial: str | None = None

        if len(cols) == 1:
            name = cols[0]
        else:
            a, b = cols[0], cols[1]
            if _looks_like_serial(a) and not _looks_like_serial(b):
                serial, name = a, b
            elif _looks_like_serial(b) and not _looks_like_serial(a):
                name, serial = a, b
            else:
                name, serial = a, b

        if not name:
            continue
        await db.create_or_update_tool(name=name, serial=serial)
        created += 1

    await state.clear()
    await m.answer(f"Импорт завершён. Обработано строк: {created}.", reply_markup=_admin_menu_kb())


@router.message(AdminDisposeTool.serial)
async def admin_dispose(m: Message, db: Database, state: FSMContext) -> None:
    serial = (m.text or "").strip()
    tool = await db.get_tool_by_serial(serial)
    if not tool:
        await m.answer("Инструмент с таким номером не найден. Введите номер ещё раз или /cancel.")
        return
    await db.set_tool_active(tool.id, False)
    await state.clear()
    await m.answer(f"Готово. Инструмент {tool.name} — {serial} списан.", reply_markup=_admin_menu_kb())


@router.message(AdminRestoreTool.serial)
async def admin_restore(m: Message, db: Database, state: FSMContext) -> None:
    serial = (m.text or "").strip()
    tool = await db.get_tool_by_serial(serial)
    if not tool:
        await m.answer("Инструмент с таким номером не найден. Введите номер ещё раз или /cancel.")
        return
    await db.set_tool_active(tool.id, True)
    await state.clear()
    await m.answer(f"Готово. Инструмент {tool.name} — {serial} восстановлен.", reply_markup=_admin_menu_kb())


@router.message(AdminAddObject.name)
async def admin_add_object_name(m: Message, db: Database, state: FSMContext) -> None:
    name = (m.text or "").strip()
    if not name:
        await m.answer("Введите непустое название объекта:")
        return
    try:
        obj_id = await db.create_object(name)
    except Exception:
        await m.answer("Не получилось создать объект (возможно, уже существует). Попробуйте другое имя или /cancel.")
        return
    await state.clear()
    await m.answer(f"Готово. Объект создан (id={obj_id}).", reply_markup=_admin_menu_kb())


@router.message(AdminImportObjects.text)
async def admin_import_objects_text(m: Message, db: Database, state: FSMContext) -> None:
    text = (m.text or "").strip()
    if not text:
        await m.answer("Пусто. Пришлите текст со списком объектов.")
        return
    created = 0
    for raw_line in text.splitlines():
        name = raw_line.strip()
        if not name or name.startswith("#"):
            continue
        try:
            await db.create_object(name)
            created += 1
        except Exception:
            continue
    await state.clear()
    await m.answer(f"Импорт объектов завершён. Создано: {created}.", reply_markup=_admin_menu_kb())