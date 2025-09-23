# app/bot_inline_form.py
# -*- coding: utf-8 -*-
import os
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from collections import defaultdict

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# >>> NEW: DB / repo
from app.db import init_db, get_session
from app.db import Currency, Category, User, Entry
from app.repo import (
    ensure_user, get_user_prefs_snapshot, add_custom_currency,
    add_custom_category, add_entry, list_user_currencies, list_user_categories
)

# NEW: SQL helpers
from sqlalchemy import select, delete

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is not set")

dp = Dispatcher()
r = Router()
dp.include_router(r)

# ================== In-memory prefs (на прод — в БД) ==================
USER_PREFS = defaultdict(lambda: {
    "currencies": [],  # общие
    "categories": {"income": [], "expense": [], "asset": []},  # по режимам
})

# ================== Константы / утилиты ==================
BASE_CURRENCIES = ["USD", "USDT", "RUB", "VND", "EUR"]
CUR_PAGE_SIZE = 12
CAT_PAGE_SIZE = 12

DEFAULT_CATEGORIES = {
    "income": [
        "Зарплата", "Премия", "Фриланс", "Кэшбэк", "Проценты", "Дивиденды",
        "Возврат налога", "Подарок", "Аренда", "Перевод", "Продажа вещи", "Другое"
    ],
    "expense": [
        "Еда", "Транспорт", "Жильё", "Коммуналка", "Одежда", "Медицина",
        "Подписки", "Подарки", "Путешествия", "Развлечения", "Образование", "Другое"
    ],
    "asset": [
        "Крипта", "Акции", "Облигации", "Фонд", "Вклад",
        "Недвижимость", "Золото", "Серебро", "Кэш", "Другое"
    ],
}

MODE_META = {
    "income": {"icon": "💰", "title": "ДОХОД"},
    "expense": {"icon": "💸", "title": "РАСХОД"},
    "asset":   {"icon": "📦", "title": "АКТИВ"},
}

def fmt_money_str(s: str) -> str:
    if not s:
        return "—"
    try:
        v = Decimal(s.replace(",", "."))
        txt = f"{v:,.2f}".replace(",", " ")
        return txt[:-3] if txt.endswith(".00") else txt
    except Exception:
        return s

def parse_amount(s: str) -> Decimal | None:
    if not s:
        return None
    t = s.replace(" ", "").replace(",", ".")
    try:
        v = Decimal(t)
        if v > 0:
            return v
    except (InvalidOperation, ValueError):
        pass
    return None

def uniq_push_front(seq: list[str], value: str, max_len: int = 50):
    value = value.strip()
    if not value:
        return
    seq[:] = [x for x in seq if x.lower() != value.lower()]
    seq.insert(0, value)
    if len(seq) > max_len:
        del seq[max_len:]

def currencies_for_user(user_id: int) -> list[str]:
    prefs = USER_PREFS[user_id]["currencies"]
    base_filtered = [c for c in BASE_CURRENCIES if all(c.lower()!=x.lower() for x in prefs)]
    return prefs + base_filtered

def categories_for_user(user_id: int, mode: str) -> list[str]:
    prefs = USER_PREFS[user_id]["categories"][mode]
    base_filtered = [c for c in DEFAULT_CATEGORIES[mode] if all(c.lower()!=x.lower() for x in prefs)]
    return prefs + base_filtered

async def safe_delete(bot: Bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

# >>> NEW: нормализация строки суммы для поля ввода (чтобы 43.00 -> "43")
def normalize_amount_input(value) -> str:
    try:
        d = Decimal(str(value))
        s = format(d, "f")          # без экспоненты
        s = s.rstrip("0").rstrip(".") or "0"
        return s
    except Exception:
        return str(value)

# ================== Состояние ==================
@dataclass
class FormState:
    main_msg_id: int | None = None
    prompt_msg_id: int | None = None    # id сообщения-подсказки для кастома
    pending_kind: str | None = None     # 'cur' | 'cat' | None
    mode: str = "income"                # income | expense | asset
    amount_str: str = ""
    currency: str | None = None
    category: str | None = None
    cur_page: int = 0
    cat_page: int = 0
    tab: str = "amount"                 # amount | currency | category

class Flow(StatesGroup):
    form = State()
    add_currency = State()
    add_category = State()

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
        InlineKeyboardButton(text="💱 Валюта (Готово)", callback_data="go:currency"),
        InlineKeyboardButton(text="🏷 Категория", callback_data="go:category"),
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

# ================== Хендлеры ==================
@r.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()

    # >>> NEW: DB user + прогрев кастомов в кэш
    async with await get_session() as session:
        await ensure_user(session, m.from_user.id, m.from_user.username)
        snap = await get_user_prefs_snapshot(session, m.from_user.id)
    USER_PREFS[m.from_user.id]["currencies"] = snap["currencies"]
    USER_PREFS[m.from_user.id]["categories"] = snap["categories"]

    st = FormState()
    await state.set_state(Flow.form)
    msg = await m.answer(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    st.main_msg_id = msg.message_id
    await state.update_data(st=st.__dict__)

@r.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()

# ----- Переключение режима (ТОЛЬКО на вкладке сумма) -----
@r.callback_query(Flow.form, F.data.startswith("mode:set:"))
async def mode_set(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":",2)[2]
    data = await state.get_data(); st = FormState(**data["st"])
    st.mode = mode
    st.category = None
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    await cb.answer(MODE_META[mode]["title"])

# --- Сумма ---
@r.callback_query(Flow.form, F.data.startswith("num:"))
async def on_num(cb: CallbackQuery, state: FSMContext):
    digit = cb.data.split(":",1)[1]
    data = await state.get_data(); st = FormState(**data["st"])
    if digit == "." and "." in st.amount_str:
        await cb.answer("Уже есть точка"); return
    if len(st.amount_str) >= 18:
        await cb.answer("Слишком длинно"); return
    st.amount_str += digit; st.tab = "amount"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    await cb.answer()

@r.callback_query(Flow.form, F.data == "backspace")
async def on_backspace(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.amount_str = st.amount_str[:-1]; st.tab = "amount"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    await cb.answer()

@r.callback_query(Flow.form, F.data == "clear")
async def on_clear(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.amount_str = ""; st.tab = "amount"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    await cb.answer("Очищено")

# --- Переходы вкладок ---
@r.callback_query(Flow.form, F.data == "go:currency")
async def go_currency(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.tab = "currency"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_currency_tab(cb.from_user.id, st), parse_mode="HTML")
    await cb.answer()

@r.callback_query(Flow.form, F.data == "go:amount")
async def go_amount(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.tab = "amount"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    await cb.answer()

@r.callback_query(Flow.form, F.data == "go:category")
async def go_category(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.tab = "category"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_category_tab(cb.from_user.id, st), parse_mode="HTML")
    await cb.answer()

# --- Валюта ---
@r.callback_query(Flow.form, F.data.startswith("cur:page:"))
async def cur_page(cb: CallbackQuery, state: FSMContext):
    page = int(cb.data.split(":")[2])
    data = await state.get_data(); st = FormState(**data["st"])
    st.cur_page = page; st.tab = "currency"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_reply_markup(reply_markup=kb_currency_tab(cb.from_user.id, st))
    await cb.answer()

@r.callback_query(Flow.form, F.data.startswith("cur:set:"))
async def cur_set(cb: CallbackQuery, state: FSMContext):
    cur = cb.data.split(":",2)[2]
    data = await state.get_data(); st = FormState(**data["st"])
    st.currency = cur
    await state.update_data(st=st.__dict__)
    st.tab = "category"; st.cat_page = 0
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_category_tab(cb.from_user.id, st), parse_mode="HTML")
    await cb.answer(f"Валюта: {cur}")

@r.callback_query(Flow.form, F.data == "cur:add")
async def cur_add_prompt(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    prompt = await cb.message.answer(
        "Введи код/название валюты (например: GBP, тенге, USDC).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✖️ Отмена ввода", callback_data="custom:cancel:cur")
        ]])
    )
    st.pending_kind = "cur"
    st.prompt_msg_id = prompt.message_id
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.add_currency)
    await cb.answer()

# ----- Спец-обработчик ОТМЕНЫ (до «блокирующего») -----
@r.callback_query(Flow.add_currency, F.data == "custom:cancel:cur")
async def cur_add_cancel(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.pending_kind = None
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.form)
    await safe_delete(cb.bot, cb.message.chat.id, cb.message.message_id)
    st.tab = "currency"
    await cb.bot.edit_message_text(
        chat_id=cb.message.chat.id,
        message_id=st.main_msg_id,
        text=render_card(st),
        reply_markup=kb_currency_tab(cb.from_user.id, st),
        parse_mode="HTML"
    )
    await cb.answer("Отменено")

# ----- Блокирующий alert во время ожидания кастома -----
@r.callback_query(Flow.add_currency)
async def lock_during_add_currency(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Сначала введи свою валюту в сообщении ниже или нажми «Отмена ввода».", show_alert=True)

@r.message(Flow.add_currency, F.text)
async def cur_add_save(m: Message, state: FSMContext):
    text = m.text.strip()

    # >>> NEW: сохранить кастом в БД и обновить кэш
    async with await get_session() as session:
        await ensure_user(session, m.from_user.id, m.from_user.username)
        await add_custom_currency(session, m.from_user.id, text)
        USER_PREFS[m.from_user.id]["currencies"] = await list_user_currencies(session, m.from_user.id)

    data = await state.get_data(); st = FormState(**data["st"])
    st.pending_kind = None
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.form)
    # обновляем ВЕРХНЕЕ окно на вкладке валют
    bot: Bot = m.bot
    st.tab = "currency"
    await bot.edit_message_text(
        chat_id=m.chat.id,
        message_id=st.main_msg_id,
        text=render_card(st),
        reply_markup=kb_currency_tab(m.from_user.id, st),
        parse_mode="HTML"
    )
    # удалить подсказку и сообщение пользователя
    await safe_delete(bot, m.chat.id, st.prompt_msg_id)
    await safe_delete(bot, m.chat.id, m.message_id)

@r.callback_query(Flow.form, F.data == "cur:manage")
async def cur_manage(cb: CallbackQuery, state: FSMContext):
    items = USER_PREFS[cb.from_user.id]["currencies"]
    await cb.message.edit_reply_markup(reply_markup=kb_manage_list(items, "cur"))
    await cb.answer()

@r.callback_query(Flow.form, F.data.startswith("mg:cur:del:"))
async def cur_del(cb: CallbackQuery, state: FSMContext):
    name = cb.data.split(":",3)[3]
    arr = USER_PREFS[cb.from_user.id]["currencies"]
    arr[:] = [x for x in arr if x.lower()!=name.lower()]

    # >>> NEW: удалить из БД тоже
    async with await get_session() as session:
        await session.execute(delete(Currency).where(Currency.user_id == cb.from_user.id, Currency.code.ilike(name)))
        await session.commit()

    await cb.message.edit_reply_markup(reply_markup=kb_manage_list(arr, "cur"))
    await cb.answer(f"Удалено: {name}")

@r.callback_query(Flow.form, F.data.startswith("mg:cur:page:"))
async def cur_mg_page(cb: CallbackQuery, state: FSMContext):
    page = int(cb.data.split(":")[3])
    items = USER_PREFS[cb.from_user.id]["currencies"]
    await cb.message.edit_reply_markup(reply_markup=kb_manage_list(items, "cur", page=page))
    await cb.answer()

@r.callback_query(Flow.form, F.data == "mg:cur:done")
async def cur_mg_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    await cb.message.edit_reply_markup(reply_markup=kb_currency_tab(cb.from_user.id, st))
    await cb.answer()

# --- Категория ---
@r.callback_query(Flow.form, F.data.startswith("cat:page:"))
async def cat_page(cb: CallbackQuery, state: FSMContext):
    _, _, mode, page = cb.data.split(":", 3)
    page = int(page)
    data = await state.get_data(); st = FormState(**data["st"])
    if mode != st.mode:
        await cb.answer(); return
    st.cat_page = page; st.tab = "category"
    await state.update_data(st=st.__dict__)
    await cb.message.edit_reply_markup(reply_markup=kb_category_tab(cb.from_user.id, st))
    await cb.answer()

@r.callback_query(Flow.form, F.data.startswith("cat:set:"))
async def cat_set(cb: CallbackQuery, state: FSMContext):
    _, _, mode, cat = cb.data.split(":", 3)
    data = await state.get_data(); st = FormState(**data["st"])
    if mode != st.mode:
        await cb.answer(); return
    st.category = cat
    await state.update_data(st=st.__dict__)
    await cb.message.edit_text(render_card(st), reply_markup=kb_category_tab(cb.from_user.id, st), parse_mode="HTML")
    await cb.answer(f"Категория: {cat}")

@r.callback_query(Flow.form, F.data.startswith("cat:add:"))
async def cat_add_prompt(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":", 2)[2]
    data = await state.get_data(); st = FormState(**data["st"])
    if mode != st.mode:
        await cb.answer(); return
    prompt = await cb.message.answer(
        "Введи название категории.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✖️ Отмена ввода", callback_data="custom:cancel:cat")
        ]])
    )
    st.pending_kind = "cat"
    st.prompt_msg_id = prompt.message_id
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.add_category)
    await cb.answer()

# Отмена — сначала
@r.callback_query(Flow.add_category, F.data == "custom:cancel:cat")
async def cat_add_cancel(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.pending_kind = None
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.form)
    await safe_delete(cb.bot, cb.message.chat.id, cb.message.message_id)
    st.tab = "category"
    await cb.bot.edit_message_text(
        chat_id=cb.message.chat.id,
        message_id=st.main_msg_id,
        text=render_card(st),
        reply_markup=kb_category_tab(cb.from_user.id, st),
        parse_mode="HTML"
    )
    await cb.answer("Отменено")

# Блокирующий alert — после обработчика отмены
@r.callback_query(Flow.add_category)
async def lock_during_add_category(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Сначала введи свою категорию в сообщении ниже или нажми «Отмена ввода».", show_alert=True)

@r.message(Flow.add_category, F.text)
async def cat_add_save(m: Message, state: FSMContext):
    text = m.text.strip()

    # >>> NEW: сохранить в БД и обновить кэш
    data = await state.get_data(); st = FormState(**data["st"])
    async with await get_session() as session:
        await ensure_user(session, m.from_user.id, m.from_user.username)
        await add_custom_category(session, m.from_user.id, st.mode, text)
        USER_PREFS[m.from_user.id]["categories"][st.mode] = await list_user_categories(session, m.from_user.id, st.mode)

    st.pending_kind = None
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.form)
    bot: Bot = m.bot
    st.tab = "category"
    await bot.edit_message_text(
        chat_id=m.chat.id,
        message_id=st.main_msg_id,
        text=render_card(st),
        reply_markup=kb_category_tab(m.from_user.id, st),
        parse_mode="HTML"
    )
    await safe_delete(bot, m.chat.id, st.prompt_msg_id)
    await safe_delete(bot, m.chat.id, m.message_id)

@r.callback_query(Flow.form, F.data.startswith("cat:manage:"))
async def cat_manage(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":", 2)[2]
    data = await state.get_data(); st = FormState(**data["st"])
    if mode != st.mode:
        await cb.answer(); return
    items = USER_PREFS[cb.from_user.id]["categories"][mode]
    await cb.message.edit_reply_markup(reply_markup=kb_manage_list(items, "cat", mode=mode))
    await cb.answer()

@r.callback_query(Flow.form, F.data.startswith("mg:cat:"))
async def cat_manage_ops(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    _, _, mode, op, *rest = parts
    data = await state.get_data(); st = FormState(**data["st"])
    if mode != st.mode:
        await cb.answer(); return
    arr = USER_PREFS[cb.from_user.id]["categories"][mode]
    if op == "del":
        name = rest[0]
        arr[:] = [x for x in arr if x.lower()!=name.lower()]

        # >>> NEW: удалить из БД тоже
        async with await get_session() as session:
            await session.execute(delete(Category).where(
                Category.user_id == cb.from_user.id, Category.mode == mode, Category.name.ilike(name)
            ))
            await session.commit()

        await cb.message.edit_reply_markup(reply_markup=kb_manage_list(arr, "cat", mode=mode))
        await cb.answer(f"Удалено: {name}")
    elif op == "page":
        page = int(rest[0])
        await cb.message.edit_reply_markup(reply_markup=kb_manage_list(arr, "cat", mode=mode, page=page))
        await cb.answer()
    elif op == "done":
        await cb.message.edit_reply_markup(reply_markup=kb_category_tab(cb.from_user.id, st))
        await cb.answer()

# --- Подтверждение ---
@r.callback_query(Flow.form, F.data == "submit")
async def submit(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    value = parse_amount(st.amount_str)
    if value is None:
        await cb.answer("Укажи корректную сумму (>0)", show_alert=True); return
    if not st.currency:
        await cb.answer("Выбери валюту", show_alert=True); return
    if not st.category:
        await cb.answer("Выбери категорию", show_alert=True); return

    # >>> NEW: записать в БД
    async with await get_session() as session:
        await ensure_user(session, cb.from_user.id, cb.from_user.username)
        await add_entry(session, cb.from_user.id, st.mode, Decimal(st.amount_str.replace(",", ".")), st.currency, st.category, note=None)

        # Определим id только что сохранённой записи (последняя по времени для пользователя)
        entry_id = await session.scalar(
            select(Entry.id)
            .where(Entry.user_id == cb.from_user.id)
            .order_by(Entry.created_at.desc())
            .limit(1)
        )

    # Сформируем клавиатуру действий (только если запись в последних 10)
    actions_kb = await build_entry_actions_kb(cb.from_user.id, entry_id) if entry_id else None

    m = MODE_META[st.mode]
    msg = (
        f"✅ Сохранено:\n\n"
        f"• {m['title']}: {fmt_money_str(st.amount_str)} {st.currency}\n"
        f"• Категория: {st.category}\n\n"
        "Начать заново: /start"
    )
    await state.clear()
    await cb.message.edit_text(msg, reply_markup=actions_kb, parse_mode="HTML")
    await cb.answer()

# ====== NEW: Обработчики действий записи (Удалить / Изменить) ======

@r.callback_query(F.data.startswith("entry:delete:"))
async def entry_delete(cb: CallbackQuery):
    try:
        entry_id = int(cb.data.split(":")[2])
    except Exception:
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return

    async with await get_session() as session:
        entry = await session.get(Entry, entry_id)
        if not entry or entry.user_id != cb.from_user.id:
            await cb.answer("Запись не найдена или нет доступа", show_alert=True)
            return
        await session.delete(entry)
        await session.commit()

    # удаляем сообщение с записью
    try:
        await cb.message.delete()
    except Exception:
        await cb.message.edit_text("❌ Запись удалена", reply_markup=None)
    await cb.answer("Удалено")

@r.callback_query(F.data.startswith("entry:edit:"))
async def entry_edit(cb: CallbackQuery, state: FSMContext):
    try:
        entry_id = int(cb.data.split(":")[2])
    except Exception:
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return

    async with await get_session() as session:
        # заберём запись
        entry = await session.get(Entry, entry_id)
        if not entry or entry.user_id != cb.from_user.id:
            await cb.answer("Запись не найдена или нет доступа", show_alert=True)
            return

        # подготовим данные для формы ДО удаления
        mode = entry.mode
        amount_str = normalize_amount_input(entry.amount)  # <<< ВАЖНО: нормализуем для продолжения ввода
        # подстрахуемся с валютой/категорией
        currency_code = None
        category_name = None
        if entry.currency_id:
            currency_code = await session.scalar(
                select(Currency.code).where(Currency.id == entry.currency_id)
            )
        if entry.category_id:
            category_name = await session.scalar(
                select(Category.name).where(Category.id == entry.category_id)
            )

        # удалим старую запись (как и задумано — заменяем на новую)
        await session.delete(entry)
        await session.commit()

    # восстановим редактор в том же сообщении
    st = FormState(
        mode=mode,
        amount_str=amount_str,
        currency=currency_code,
        category=category_name,
        tab="amount",
    )
    await state.set_state(Flow.form)
    await state.update_data(st=st.__dict__)

    msg = await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    st.main_msg_id = msg.message_id
    await state.update_data(st=st.__dict__)
    await cb.answer("Редактирование")

# ================== Запуск ==================
async def main():
    # >>> NEW: инициализация БД один раз
    await init_db()
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
