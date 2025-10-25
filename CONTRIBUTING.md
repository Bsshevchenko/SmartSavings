# 🤝 Руководство по вкладу в SmartSavings

Спасибо за интерес к проекту SmartSavings! Мы приветствуем вклад от сообщества.

## 🚀 Быстрый старт для разработчиков

### 📋 Предварительные требования

- Python 3.12+
- Git
- Telegram Bot Token (для тестирования)
- Docker (опционально)

### 🛠️ Настройка окружения разработки

1. **Fork и клонирование:**
```bash
git clone https://github.com/your-username/SmartSavings.git
cd SmartSavings
```

2. **Создание виртуального окружения:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

3. **Установка зависимостей:**
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Дополнительные dev зависимости
```

4. **Настройка .env:**
```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

## 🏗️ Архитектура для разработчиков

### 📁 Структура кода

```
app/
├── 🚀 main.py              # Точка входа
├── ⚙️ config.py            # Конфигурация
├── 🗄️ db/                 # База данных
├── 🛣️ routers/            # Обработчики команд
├── 🎯 states/             # FSM состояния
├── ⌨️ keyboards/          # UI компоненты
├── 🏪 repo/               # Слой данных
├── 🔧 services/           # Бизнес-логика
├── ⏰ scheduler/          # Планировщик
└── 🛠️ utils/             # Утилиты
```

### 🎯 Принципы разработки

1. **Разделение ответственности:**
   - `routers/` — только обработка Telegram команд
   - `services/` — бизнес-логика
   - `repo/` — доступ к данным
   - `keyboards/` — UI компоненты

2. **Типизация:**
   - Используйте type hints везде
   - Pydantic для валидации данных

3. **Асинхронность:**
   - Все операции с БД асинхронные
   - Используйте `async/await`

## 🧪 Тестирование

### 🏃‍♂️ Запуск тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=app --cov-report=html

# Конкретный тест
pytest tests/test_repo.py::test_add_entry
```

### 📝 Написание тестов

```python
# tests/test_repo.py
import pytest
from app.repo.repo import add_entry
from app.db.models import Entry

@pytest.mark.asyncio
async def test_add_entry():
    # Arrange
    session = await get_test_session()
    
    # Act
    entry = await add_entry(
        session=session,
        user_id=123,
        mode="expense",
        amount=100.50,
        currency_id=1,
        category_id=1
    )
    
    # Assert
    assert entry.amount == 100.50
    assert entry.mode == "expense"
```

## 📝 Стандарты кода

### 🎨 Форматирование

```bash
# Автоматическое форматирование
black app/ tests/
isort app/ tests/

# Проверка стиля
flake8 app/ tests/
```

### 🔍 Проверка типов

```bash
# Проверка типов
mypy app/

# Строгая проверка
mypy --strict app/
```

### 🛡️ Безопасность

```bash
# Проверка безопасности
bandit -r app/
safety check
```

## 🔀 Workflow разработки

### 🌿 Создание feature branch

```bash
# Создание новой ветки
git checkout -b feature/amazing-feature

# Или для исправления багов
git checkout -b fix/bug-description
```

### 📝 Commit сообщения

Используйте [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: добавить поддержку новых валют
fix: исправить ошибку в расчете баланса
docs: обновить документацию API
test: добавить тесты для repo слоя
refactor: рефакторинг keyboard компонентов
```

### 🔄 Pull Request процесс

1. **Создайте PR** с описанием изменений
2. **Убедитесь**, что все тесты проходят
3. **Добавьте тесты** для новой функциональности
4. **Обновите документацию** при необходимости
5. **Дождитесь review** от maintainers

## 🐛 Отчеты об ошибках

### 📋 Шаблон для bug report

```markdown
## 🐛 Описание ошибки
Краткое описание проблемы

## 🔄 Шаги для воспроизведения
1. Перейти к '...'
2. Нажать на '...'
3. Увидеть ошибку

## 🎯 Ожидаемое поведение
Что должно было произойти

## 📱 Окружение
- OS: [e.g. macOS, Windows, Linux]
- Python: [e.g. 3.12.0]
- Версия бота: [e.g. v1.0.0]

## 📎 Дополнительная информация
Скриншоты, логи, etc.
```

## 💡 Предложения улучшений

### 🚀 Шаблон для feature request

```markdown
## 💡 Описание функции
Краткое описание предлагаемой функции

## 🎯 Проблема
Какую проблему решает эта функция?

## 💭 Предлагаемое решение
Подробное описание решения

## 🔄 Альтернативы
Другие варианты решения

## 📎 Дополнительная информация
Скриншоты, mockups, etc.
```

## 📚 Полезные ресурсы

### 🔗 Документация

- [aiogram 3.x](https://docs.aiogram.dev/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/)
- [Pydantic](https://docs.pydantic.dev/)
- [pytest](https://docs.pytest.org/)

### 🛠️ Инструменты разработки

- [Black](https://black.readthedocs.io/) — Форматирование кода
- [isort](https://pycqa.github.io/isort/) — Сортировка импортов
- [mypy](https://mypy.readthedocs.io/) — Проверка типов
- [pytest](https://pytest.org/) — Тестирование

## 🏷️ Версионирование

Проект использует [Semantic Versioning](https://semver.org/):

- **MAJOR** — несовместимые изменения API
- **MINOR** — новая функциональность (обратно совместимая)
- **PATCH** — исправления багов (обратно совместимые)

## 📞 Поддержка

- 💬 [Telegram чат](https://t.me/smartsavings_dev)
- 📧 Email: support@smartsavings.dev
- 🐛 [Issues](https://github.com/your-username/SmartSavings/issues)

## 🎉 Спасибо!

Спасибо за вклад в SmartSavings! Каждый PR, issue и предложение делают проект лучше.

---

**Happy coding! 🚀**
