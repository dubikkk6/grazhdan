from aiogram.fsm.state import State, StatesGroup


class MoveToolFlow(StatesGroup):
    from_object_id = State()
    tool_id = State()
    to_object_id = State()
    confirm = State()


class AdminAddTool(StatesGroup):
    name = State()
    serial = State()


class AdminImportTools(StatesGroup):
    csv_text = State()


class AdminAddObject(StatesGroup):
    name = State()


class AdminDisposeTool(StatesGroup):
    serial = State()


class AdminRestoreTool(StatesGroup):
    serial = State()


class AdminImportObjects(StatesGroup):
    text = State()


class AdminDeleteObject(StatesGroup):
    confirm = State()  # состояние для подтверждения удаления