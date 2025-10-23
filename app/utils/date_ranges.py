from datetime import datetime, timedelta, timezone


def get_today_range():
    # Используем локальное время, так как данные в БД сохранены в локальном времени
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now
    return start, end


def get_this_week_range():
    now = datetime.now()
    start = now - timedelta(days=now.weekday())  # Понедельник
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now
    return start, end

def get_this_month_range():
    now = datetime.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now
    return start, end

def get_month_range(target_date: datetime) -> tuple[datetime, datetime]:
    """Возвращает начало и конец месяца для указанной даты."""
    start = target_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end
