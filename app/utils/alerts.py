"""
Утилиты для отправки алертов об ошибках в Telegram.

Модуль предоставляет обработчик логов `TelegramAlertHandler`, который перехватывает
сообщения уровня WARNING и выше и отправляет их в указанные чаты Telegram с помощью
отдельного бота для алертов. Для подключения достаточно вызвать `setup_alert_logging()`
при старте приложения (например, в `app/main.py`).

Переменные окружения:
- TELEGRAM_BOT_ALERT — токен Telegram-бота для алёртов (обязателен для отправки).
- TELEGRAM_ALERT_CHAT_ID — идентификатор(-ы) чатов (user/group) через запятую.
  Пример: "123456789,-1001234567890". Если значения не заданы, обработчик работает как no-op.
"""
import asyncio
import logging
import os
from typing import Iterable, List, Optional

try:
    from aiogram import Bot
except Exception:  # pragma: no cover
    Bot = None  # type: ignore

from app.config import settings


class TelegramAlertHandler(logging.Handler):
    """Обработчик логов, отправляющий записи уровня WARNING+ в Telegram через отдельного бота.

    Использует токен из переменной окружения `TELEGRAM_BOT_ALERT` и список чатов
    из `TELEGRAM_ALERT_CHAT_ID`. Если токен или список чатов не заданы, обработчик
    не выполняет отправку (no-op).
    """

    def __init__(self, level: int = logging.WARNING) -> None:
        super().__init__(level=level)
        self._token: Optional[str] = settings.TELEGRAM_BOT_ALERT
        self._chat_ids: List[int] = self._parse_chat_ids(settings.TELEGRAM_ALERT_CHAT_ID)
        self._bot: Optional[Bot] = None

        if self._token and Bot is not None:
            self._bot = Bot(token=self._token)

    @staticmethod
    def _parse_chat_ids(raw: Optional[str]) -> List[int]:
        if not raw:
            return []
        ids: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                try:
                    ids.append(int(part))
                except Exception:
                    continue
        return ids

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        if self._bot is None or not self._chat_ids:
            return

        try:
            msg = self.format(record)
            if record.exc_info and not msg:
                msg = logging.Formatter().formatException(record.exc_info)  # type: ignore[arg-type]

            asyncio.create_task(self._send(msg))
        except Exception:
            pass

    async def _send(self, text: str) -> None:
        assert self._bot is not None
        for chat_id in self._chat_ids:
            try:
                await self._bot.send_message(chat_id=chat_id, text=f"🚨 Alert:\n{text}")
            except Exception:
                continue


def setup_alert_logging() -> None:
    """Подключает `TelegramAlertHandler` к корневому логгеру на уровне WARNING.

    Функцию можно вызывать многократно — дубликаты обработчика не будут добавлены.
    """
    handler = TelegramAlertHandler(level=logging.WARNING)
    root = logging.getLogger()

    if not any(isinstance(h, TelegramAlertHandler) for h in root.handlers):
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    if root.level > logging.WARNING:
        root.setLevel(logging.WARNING)
