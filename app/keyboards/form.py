from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from app.db import get_session
from app.db.models import Entry
from app.states.form import FormState
from app.utils.formatting import fmt_money_str, currencies_for_user, categories_for_user
from app.constants.constants import MODE_META, CAT_PAGE_SIZE, CUR_PAGE_SIZE


# ================== Рендер карточки ==================
def render_card(st: FormState) -> str:
    m = MODE_META[st.mode]
    return (
        f"{m['icon']} {m['title']}\n\n"
        f"Сумма: <b>{fmt_money_str(st.amount_str)}</b>\n"
        f"Валюта: <b>{st.currency or '—'}</b>\n"
        f"Категория: <b>{st.category or '—'}</b>\n\n"
        "Сначала введи сумму, затем выбери валюту и категорию. Можно переходить между вкладками."
    )

# ================== Клавиатуры (без изменений) ==================
def kb_mode_tabs(st: FormState) -> list[InlineKeyboardButton]:
    def lab(m):
        meta = MODE_META[m]
        active = "● " if st.mode == m else ""
        return InlineKeyboardButton(text=f"{active}{meta['title']}", callback_data=f"mode:set:{m}")
    return [lab("income"), lab("expense"), lab("asset")]

def kb_amount_tab(st: FormState) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(*kb_mode_tabs(st))
    for row in [["1","2","3"],["4","5","6"],["7","8","9"],[".","0","⌫"]]:
        btns = []
        for t in row:
            cb = "num:" + (t if t != "," else ".")
            if t == "⌫":
                cb = "backspace"
            btns.append(InlineKeyboardButton(text=t, callback_data=cb))
        kb.row(*btns)
    kb.row(InlineKeyboardButton(text="🧹 Очистить", callback_data="clear"))
    kb.row(
        InlineKeyboardButton(text="🏷 Категория", callback_data="go:category"),
        InlineKeyboardButton(text="💱 Валюта", callback_data="go:currency"),
    )
    kb.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="submit"))
    return kb.as_markup()

def kb_currency_tab(user_id: int, st: FormState) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    all_cur = currencies_for_user(user_id)
    start = st.cur_page * CUR_PAGE_SIZE
    chunk = all_cur[start:start+CUR_PAGE_SIZE]
    row_buf = []
    for i, c in enumerate(chunk, 1):
        mark = " ✅" if st.currency and st.currency.lower()==c.lower() else ""
        row_buf.append(InlineKeyboardButton(text=c+mark, callback_data=f"cur:set:{c}"))
        if i % 4 == 0:
            kb.row(*row_buf); row_buf = []
    if row_buf: kb.row(*row_buf)
    total_pages = (len(all_cur)-1)//CUR_PAGE_SIZE + 1 if all_cur else 1
    left = max(st.cur_page-1, 0); right = min(st.cur_page+1, total_pages-1)
    kb.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"cur:page:{left}"),
        InlineKeyboardButton(text=f"{st.cur_page+1}/{total_pages}", callback_data="noop"),
        InlineKeyboardButton(text="➡️", callback_data=f"cur:page:{right}"),
    )
    kb.row(
        InlineKeyboardButton(text="➕ Своя валюта", callback_data="cur:add"),
        InlineKeyboardButton(text="🗑 Удалить валюты", callback_data="cur:manage"),
    )
    kb.row(
        InlineKeyboardButton(text="⬅️ Сумма", callback_data="go:amount"),
        InlineKeyboardButton(text="🏷 Категория", callback_data=f"go:category"),
    )
    kb.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="submit"))
    return kb.as_markup()

def kb_category_tab(user_id: int, st: FormState) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    all_cat = categories_for_user(user_id, st.mode)
    start = st.cat_page * CAT_PAGE_SIZE
    chunk = all_cat[start:start+CAT_PAGE_SIZE]
    row_buf = []
    for i, t in enumerate(chunk, 1):
        mark = " ✅" if st.category and st.category.lower()==t.lower() else ""
        row_buf.append(InlineKeyboardButton(text=t+mark, callback_data=f"cat:set:{st.mode}:{t}"))
        if i % 3 == 0:
            kb.row(*row_buf); row_buf = []
    if row_buf: kb.row(*row_buf)
    total_pages = (len(all_cat)-1)//CAT_PAGE_SIZE + 1 if all_cat else 1
    left = max(st.cat_page-1, 0); right = min(st.cat_page+1, total_pages-1)
    kb.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"cat:page:{st.mode}:{left}"),
        InlineKeyboardButton(text=f"{st.cat_page+1}/{total_pages}", callback_data="noop"),
        InlineKeyboardButton(text="➡️", callback_data=f"cat:page:{st.mode}:{right}"),
    )
    kb.row(
        InlineKeyboardButton(text="➕ Своя категория", callback_data=f"cat:add:{st.mode}"),
        InlineKeyboardButton(text="🗑 Удалить категории", callback_data=f"cat:manage:{st.mode}"),
    )
    kb.row(
        InlineKeyboardButton(text="⬅️ Сумма", callback_data="go:amount"),
        InlineKeyboardButton(text="💱 Валюта", callback_data="go:currency"),
    )
    kb.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="submit"))
    return kb.as_markup()

def kb_manage_list(items: list[str], kind: str, mode: str | None = None, page: int = 0, page_size: int = 12) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    start = page*page_size; chunk = items[start:start+page_size]
    row_buf = []
    for i, it in enumerate(chunk, 1):
        cb = f"mg:cur:del:{it}" if kind=="cur" else f"mg:cat:{mode}:del:{it}"
        row_buf.append(InlineKeyboardButton(text=f"❌ {it}", callback_data=cb))
        if i % 3 == 0:
            kb.row(*row_buf); row_buf=[]
    if row_buf: kb.row(*row_buf)
    total_pages = (len(items)-1)//page_size + 1 if items else 1
    left = max(page-1, 0); right = min(page+1, total_pages-1)
    if kind=="cur":
        kb.row(
            InlineKeyboardButton(text="⬅️", callback_data=f"mg:cur:page:{left}"),
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"),
            InlineKeyboardButton(text="➡️", callback_data=f"mg:cur:page:{right}"),
        )
        kb.row(InlineKeyboardButton(text="↩️ Готово", callback_data="mg:cur:done"))
    else:
        kb.row(
            InlineKeyboardButton(text="⬅️", callback_data=f"mg:cat:{mode}:page:{left}"),
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"),
            InlineKeyboardButton(text="➡️", callback_data=f"mg:cat:{mode}:page:{right}"),
        )
        kb.row(InlineKeyboardButton(text="↩️ Готово", callback_data=f"mg:cat:{mode}:done"))
    return kb.as_markup()

# ================== ВСПОМОГАТЕЛЬНОЕ: кнопки действий записи ==================

async def build_entry_actions_kb(user_id: int, entry_id: int) -> InlineKeyboardMarkup | None:
    """
    Возвращает клавиатуру с кнопками Удалить/Изменить,
    только если entry_id входит в последние 10 записей пользователя.
    """
    async with await get_session() as session:
        last_ids = (await session.scalars(
            select(Entry.id)
            .where(Entry.user_id == user_id)
            .order_by(Entry.created_at.desc())
            .limit(10)
        )).all()
    if entry_id in last_ids:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"entry:delete:{entry_id}"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"entry:edit:{entry_id}")
        ]])
    return None