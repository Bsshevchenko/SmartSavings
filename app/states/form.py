from dataclasses import dataclass
from aiogram.fsm.state import StatesGroup, State

@dataclass
class FormState:
    """UI-снимок формы ввода транзакции (живёт в FSM storage)."""
    main_msg_id: int | None = None
    prompt_msg_id: int | None = None
    pending_kind: str | None = None       # 'cur' | 'cat' | 'note' | None
    mode: str = "expense"                  # income | expense | asset
    amount_str: str = ""
    currency: str | None = None
    category: str | None = None
    note: str | None = None
    cur_page: int = 0
    cat_page: int = 0
    tab: str = "amount"                   # amount | currency | category

class Flow(StatesGroup):
    """Стадии сценария формы ввода."""
    form = State()
    add_currency = State()
    add_category = State()
    add_note = State()
