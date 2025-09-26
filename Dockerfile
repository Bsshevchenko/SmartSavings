# Базовый образ
FROM python:3.12-slim

# Устанавливаем зависимости системы (для psycopg2, aiogram и т.п.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY app ./app

# Запускаем бота
CMD ["python", "-m", "app.main"]
