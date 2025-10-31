from decimal import Decimal
from datetime import datetime, timezone
from aiogram import Router, F, Bot
from sqlalchemy import select, delete
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.db import get_session
from app.db.models import Currency, Category, Entry
from app.states.form import FormState, Flow
from app.keyboards.form import render_card, kb_amount_tab, kb_currency_tab, kb_category_tab, kb_manage_list, \
    build_entry_actions_kb
from app.constants.constants import USER_PREFS, MODE_META, BASE_CURRENCIES, DEFAULT_CATEGORIES
from app.repo.repo import (
    ensure_user, get_user_prefs_snapshot, add_custom_currency,
    add_custom_category, add_entry, list_user_currencies, list_user_categories,
    update_currency_last_used, update_category_last_used
)
from app.utils.formatting import safe_delete, parse_amount, fmt_money_str, normalize_amount_input, uniq_push_front

r = Router()

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
    
    # >>> Переместить выбранную валюту в начало списка в памяти (быстро, без БД)
    prefs = USER_PREFS[cb.from_user.id]["currencies"]
    uniq_push_front(prefs, cur)
    
    # >>> Обновить last_used_at в БД асинхронно (не блокируем UI)
    # Используем один запрос вместо множественных
    async with await get_session() as session:
        # Получаем объект и обновляем за один раз
        currency_obj = (await session.execute(
            select(Currency).where(Currency.user_id == cb.from_user.id, Currency.code.ilike(cur))
        )).scalar_one_or_none()
        
        if currency_obj is None:
            # Создаем новую валюту
            currency_obj = Currency(user_id=cb.from_user.id, code=cur, last_used_at=datetime.now(timezone.utc))
            session.add(currency_obj)
        else:
            # Обновляем время последнего использования
            currency_obj.last_used_at = datetime.now(timezone.utc)
        await session.commit()
    
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
    
    # >>> переместить выбранную категорию в начало списка в памяти (быстро, без БД)
    prefs = USER_PREFS[cb.from_user.id]["categories"][mode]
    uniq_push_front(prefs, cat)
    
    # >>> обновить last_used_at в БД асинхронно (не блокируем UI)
    # Используем один запрос вместо множественных
    async with await get_session() as session:
        # Получаем объект и обновляем за один раз
        category_obj = (await session.execute(
            select(Category).where(Category.user_id == cb.from_user.id, Category.mode == mode, Category.name.ilike(cat))
        )).scalar_one_or_none()
        
        if category_obj is None:
            # Создаем новую категорию
            category_obj = Category(user_id=cb.from_user.id, mode=mode, name=cat, last_used_at=datetime.now(timezone.utc))
            session.add(category_obj)
        else:
            # Обновляем время последнего использования
            category_obj.last_used_at = datetime.now(timezone.utc)
        await session.commit()
    
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

# --- Описание ---
@r.callback_query(Flow.form, F.data == "note:add")
async def note_add_prompt(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    
    # Если уже есть описание, очищаем его
    if st.note:
        st.note = None
        await state.update_data(st=st.__dict__)
        
        # Определяем текущую вкладку и обновляем соответствующую клавиатуру
        if st.tab == "amount":
            reply_markup = kb_amount_tab(st)
        elif st.tab == "currency":
            reply_markup = kb_currency_tab(cb.from_user.id, st)
        elif st.tab == "category":
            reply_markup = kb_category_tab(cb.from_user.id, st)
        else:
            reply_markup = kb_amount_tab(st)
        
        await cb.message.edit_text(render_card(st), reply_markup=reply_markup, parse_mode="HTML")
        await cb.answer("Описание удалено")
        return
    
    prompt = await cb.message.answer(
        "Введи описание транзакции.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✖️ Отмена ввода", callback_data="custom:cancel:note")
        ]])
    )
    st.pending_kind = "note"
    st.prompt_msg_id = prompt.message_id
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.add_note)
    await cb.answer()

# Отмена ввода описания
@r.callback_query(Flow.add_note, F.data == "custom:cancel:note")
async def note_add_cancel(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); st = FormState(**data["st"])
    st.pending_kind = None
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.form)
    await safe_delete(cb.bot, cb.message.chat.id, cb.message.message_id)
    
    # Определяем текущую вкладку и обновляем соответствующую клавиатуру
    if st.tab == "amount":
        reply_markup = kb_amount_tab(st)
    elif st.tab == "currency":
        reply_markup = kb_currency_tab(cb.from_user.id, st)
    elif st.tab == "category":
        reply_markup = kb_category_tab(cb.from_user.id, st)
    else:
        reply_markup = kb_amount_tab(st)
    
    await cb.bot.edit_message_text(
        chat_id=cb.message.chat.id,
        message_id=st.main_msg_id,
        text=render_card(st),
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    await cb.answer("Отменено")

# Блокирующий alert во время ожидания ввода описания
@r.callback_query(Flow.add_note)
async def lock_during_add_note(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Сначала введи описание в сообщении ниже или нажми «Отмена ввода».", show_alert=True)

@r.message(Flow.add_note, F.text)
async def note_add_save(m: Message, state: FSMContext):
    text = m.text.strip()

    data = await state.get_data(); st = FormState(**data["st"])
    st.note = text
    st.pending_kind = None
    await state.update_data(st=st.__dict__)
    await state.set_state(Flow.form)
    
    # Определяем текущую вкладку и обновляем соответствующую клавиатуру
    if st.tab == "amount":
        reply_markup = kb_amount_tab(st)
    elif st.tab == "currency":
        reply_markup = kb_currency_tab(m.from_user.id, st)
    elif st.tab == "category":
        reply_markup = kb_category_tab(m.from_user.id, st)
    else:
        reply_markup = kb_amount_tab(st)
    
    bot: Bot = m.bot
    await bot.edit_message_text(
        chat_id=m.chat.id,
        message_id=st.main_msg_id,
        text=render_card(st),
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    # удалить подсказку и сообщение пользователя
    await safe_delete(bot, m.chat.id, st.prompt_msg_id)
    await safe_delete(bot, m.chat.id, m.message_id)

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
        await add_entry(session, cb.from_user.id, st.mode, Decimal(st.amount_str.replace(",", ".")), st.currency, st.category, note=st.note)

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
        f"• Категория: {st.category}\n"
        f"• Описание: {st.note or '—'}\n\n"
        "Начать заново: /start"
    )
    await state.clear()
    await cb.message.edit_text(msg, reply_markup=actions_kb, parse_mode="HTML")
    await cb.answer()

# ====== Обработчики действий записи (Удалить / Изменить) ======

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
        
        # Если удаляем актив, нужно обновить последние значения
        if entry.mode == "asset":
            from app.services.asset_service import AssetService
            analytics_service = AssetService(session)
            
            # Получаем информацию о валюте и категории перед удалением
            currency_result = await session.execute(
                select(Currency.code).where(Currency.id == entry.currency_id)
            )
            currency_code = currency_result.scalar()
            
            category_result = await session.execute(
                select(Category.name).where(Category.id == entry.category_id)
            )
            category_name = category_result.scalar()
            
            # Удаляем запись из AssetLatestValues если это была последняя запись по этой комбинации
            if currency_code and category_name:
                # Проверяем, есть ли другие записи по этой валюте + категории
                other_entries_result = await session.execute(
                    select(Entry)
                    .where(Entry.user_id == entry.user_id)
                    .where(Entry.mode == "asset")
                    .where(Entry.currency_id == entry.currency_id)
                    .where(Entry.category_id == entry.category_id)
                    .where(Entry.id != entry_id)
                    .order_by(Entry.created_at.desc())
                )
                other_entries = other_entries_result.scalars().all()
                
                if other_entries:
                    # Если есть другие записи, обновляем на последнюю
                    latest_entry = other_entries[0]
                    await analytics_service.update_latest_asset_value(
                        entry.user_id, currency_code, category_name, 
                        latest_entry.amount, latest_entry.id
                    )
                else:
                    # Если это была последняя запись, удаляем из AssetLatestValues
                    from app.db.models import AssetLatestValues
                    asset_value_result = await session.execute(
                        select(AssetLatestValues)
                        .where(AssetLatestValues.user_id == entry.user_id)
                        .where(AssetLatestValues.currency_code == currency_code)
                        .where(AssetLatestValues.category_name == category_name)
                    )
                    asset_value = asset_value_result.scalar_one_or_none()
                    if asset_value:
                        await session.delete(asset_value)
        
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
        note = entry.note
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
        note=note,
        tab="amount",
    )
    await state.set_state(Flow.form)
    await state.update_data(st=st.__dict__)

    msg = await cb.message.edit_text(render_card(st), reply_markup=kb_amount_tab(st), parse_mode="HTML")
    st.main_msg_id = msg.message_id
    await state.update_data(st=st.__dict__)
    await cb.answer("Редактирование")
