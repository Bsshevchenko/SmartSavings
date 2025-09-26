from aiogram import Bot
from decimal import Decimal, InvalidOperation
from app.constants.constants import DEFAULT_CATEGORIES, BASE_CURRENCIES, USER_PREFS


def fmt_money_str(s: str) -> str:
    """Форматирование суммы для отображения в боте SmartSavings.

    Используется при выводе числовых значений пользователю (баланс, траты, накопления),
    чтобы суммы выглядели читабельно: с пробелами-разделителями тысяч и округлением.

    Args:
        s (str): Строка с числовым значением.

    Returns:
        str: Отформатированная строка, например '1 234.56' или '1 234',
             либо исходная строка, если преобразование не удалось.
    """
    if not s:
        return "—"
    try:
        v = Decimal(s.replace(",", "."))
        txt = f"{v:,.2f}".replace(",", " ")
        return txt[:-3] if txt.endswith(".00") else txt
    except Exception:
        return s


def parse_amount(s: str) -> Decimal | None:
    """Парсинг суммы, введённой пользователем в чат SmartSavings.

    Преобразует строку в Decimal для дальнейшей работы с балансами и транзакциями.
    Используется в хэндлерах ввода сумм.

    Args:
        s (str): Строка с числовым значением (ввод пользователя).

    Returns:
        Decimal | None: Числовое значение, если ввод корректный и > 0,
                        иначе None (например, если пользователь ввёл мусор).
    """
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
    """Добавляет значение в начало истории ввода пользователя.

    Применяется для хранения часто используемых категорий или валют,
    чтобы в интерфейсе SmartSavings пользователь видел последние выбранные значения.

    Args:
        seq (list[str]): Список последних значений (например, категорий).
        value (str): Новое значение для сохранения.
        max_len (int, optional): Максимальная длина истории. По умолчанию 50.
    """
    value = value.strip()
    if not value:
        return
    seq[:] = [x for x in seq if x.lower() != value.lower()]
    seq.insert(0, value)
    if len(seq) > max_len:
        del seq[max_len:]


def currencies_for_user(user_id: int) -> list[str]:
    """Возвращает список валют для конкретного пользователя.

    Используется при отображении интерфейса выбора валюты в боте SmartSavings.
    Сначала подставляются пользовательские предпочтения, затем добавляются базовые валюты.

    Args:
        user_id (int): ID пользователя.

    Returns:
        list[str]: Список валют, включая выбранные пользователем и стандартные (RUB, USD и др.).
    """
    prefs = USER_PREFS[user_id]["currencies"]
    base_filtered = [c for c in BASE_CURRENCIES if all(c.lower()!=x.lower() for x in prefs)]
    return prefs + base_filtered


def categories_for_user(user_id: int, mode: str) -> list[str]:
    """Возвращает список категорий расходов/доходов для пользователя.

    Применяется в меню добавления транзакций в SmartSavings.
    Сначала берутся сохранённые предпочтения пользователя, затем добавляются дефолтные категории.

    Args:
        user_id (int): ID пользователя.
        mode (str): Режим категорий — например, 'income' или 'expense'.

    Returns:
        list[str]: Список категорий, включающий пользовательские и дефолтные.
    """
    prefs = USER_PREFS[user_id]["categories"][mode]
    base_filtered = [c for c in DEFAULT_CATEGORIES[mode] if all(c.lower()!=x.lower() for x in prefs)]
    return prefs + base_filtered


async def safe_delete(bot: Bot, chat_id: int, message_id: int | None):
    """Безопасное удаление сообщений в чате.

    Используется в интерфейсе SmartSavings для очистки временных сообщений,
    чтобы чат оставался аккуратным (например, при замене inline-клавиатуры).

    Args:
        bot (Bot): Экземпляр бота.
        chat_id (int): ID чата.
        message_id (int | None): ID сообщения для удаления.
    """
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def normalize_amount_input(value) -> str:
    """Нормализация пользовательского ввода суммы.

    Применяется при сохранении транзакций в SmartSavings,
    чтобы убрать лишние нули и точку (например, '43.00' -> '43').

    Args:
        value: Введённое пользователем значение суммы (строка или число).

    Returns:
        str: Нормализованная строка суммы.
    """
    try:
        d = Decimal(str(value))
        s = format(d, "f")          # без экспоненты
        s = s.rstrip("0").rstrip(".") or "0"
        return s
    except Exception:
        return str(value)
