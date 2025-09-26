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
│   └─ analytics.py        # Роутер для аналитики (будущий модуль)
│
├─ repo/                   # Тонкий слой доступа к БД (CRUD, SQLAlchemy)
│   ├─ __init__.py
│   └─ repo.py
│
├─ db/
│   ├─ __init__.py         # init_db, get_session
│   ├─ models.py           # User, Entry, Currency, Category
│
└─ utils/
    └─ formatting.py       # Утилиты
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