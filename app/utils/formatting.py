from aiogram import Bot
from decimal import Decimal, InvalidOperation
from app.constants.constants import DEFAULT_CATEGORIES, BASE_CURRENCIES, USER_PREFS


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

def normalize_amount_input(value) -> str:
    """Нормализация строки суммы для поля ввода (чтобы 43.00 -> "43")"""
    try:
        d = Decimal(str(value))
        s = format(d, "f")          # без экспоненты
        s = s.rstrip("0").rstrip(".") or "0"
        return s
    except Exception:
        return str(value)
