from dotenv import load_dotenv
load_dotenv()

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """Конфигурация приложения SmartSavings.

    Используется для централизованного доступа к настройкам проекта,
    которые подгружаются из файла `.env`. В основном применяется
    для инициализации бота и подключения к базе данных.

    Атрибуты:
        TELEGRAM_BOT_TOKEN (str): Токен Telegram-бота, необходимый для запуска SmartSavings.
        DB_URL (str): URL подключения к базе данных (например, SQLite или PostgreSQL).
    """
    TELEGRAM_BOT_TOKEN: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    DB_URL: str = Field(..., alias="DB_URL")
    TELEGRAM_BOT_ALERT: str | None = Field(default=None, alias="TELEGRAM_BOT_ALERT")
    TELEGRAM_ALERT_CHAT_ID: str | None = Field(default=None, alias="TELEGRAM_ALERT_CHAT_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
