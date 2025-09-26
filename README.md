# Smart Savings - Умные Сбережения

Телеграмм Бот предназначенный для аналитики и управления финансами.

### Архитектурв
```
app/
├─ main.py                 # Точка входа: создание Bot/DP, регистрация роутеров
├─ config.py               # Настройки (Pydantic BaseSettings)
│
├─ states/
│   └─ form.py             # FSM + FormState dataclass
│
├─ keyboards/
│   └─ form.py             # Вся верстка инлайн-клавиатур (UI)
│
├─ routers/
│   ├─ entries.py          # Роутер для ввода данных через TG клавиатуру
│   └─ analytics.py        # Роуткр для аналитики (будущий модуль)
│
├─ services/
│   ├─ entries.py          # Бизнес-логика: валидации, транзакции, доменные операции
│   └─ prefs.py            # Работа с пользовательскими предпочтениями (валюты/категории)
│
├─ repo/                   # Тонкий слой доступа к БД (CRUD, SQLAlchemy)
│   ├─ __init__.py
│   ├─ users.py
│   ├─ entries.py
│   ├─ currencies.py
│   └─ categories.py
│
├─ db/
│   ├─ __init__.py         # init_db, get_session
│   ├─ models.py           # User, Entry, Currency, Category
│   └─ uow.py              # (опционально) UnitOfWork для транзакций
│
├─ schemas/                # Pydantic-DTO (на вход/выход сервисов и роутеров)
│   └─ entries.py
│
└─ utils/
    ├─ formatting.py       # fmt_money_str, parse_amount, normalize_amount_input
    └─ pagination.py       # вспомогалки для постранички
```


* **keyboards/** — только построение InlineKeyboardMarkup. Никакой логики/БД.
* **routers**/ — только хендлеры aiogram: читают состояние, зовут services/, обновляют UI.
* **services**/ — «умная» логика: проверки, агрегации, вызовы нескольких репозиториев в одной транзакции.
* **repo**/ — «глупые» функции CRUD поверх SQLAlchemy (ничего не знают о Telegram).
* **db**/ — инициализация SQLAlchemy, модели.
* **states**/ — все StatesGroup + твой FormState.
* **utils**/ — форматирование денег, парсинг чисел и т.п.
* **config.py** — TELEGRAM_BOT_TOKEN, строки подключений.
* **analytics.py** (router + service) — модуль чтения из БД, построение ответов / инлайн-отчётов.