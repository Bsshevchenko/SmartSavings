from app.utils.formatting import fmt_money_str, fmt_crypto_str, format_ru_month_label


def report_for_expense(label: str, totals: dict) -> str:
    """Формирует текстовый отчёт о расходах для пользователя."""
    return "\n".join([
        f"📅 {label}:",
        f"• 🇷🇺 {fmt_money_str(str(totals['RUB']))} RUB",
        f"• 🇺🇸 {fmt_money_str(str(totals['USD']))} USD",
        f"• 🇻🇳 {fmt_money_str(str(totals['VND']))} VND"
    ])


def report_for_income(label: str, totals: dict) -> str:
    """Формирует текстовый отчёт о доходах для пользователя."""
    return "\n".join([
        f"💰 {label}:",
        f"• 🇷🇺 {fmt_money_str(str(totals['RUB']))} RUB",
        f"• 🇺🇸 {fmt_money_str(str(totals['USD']))} USD",
        f"• 🇻🇳 {fmt_money_str(str(totals['VND']))} VND"
    ])


def report_for_assets(label: str, totals: dict) -> str:
    """Формирует текстовый отчёт о капитале для пользователя."""
    return "\n".join([
        f"💰 Капитал на {label}:",
        f"• 🇷🇺 {fmt_money_str(str(totals['RUB']))} RUB",
        f"• 🇺🇸 {fmt_money_str(str(totals['USD']))} USD",
    ])


def report_asset_growth(prev_date, current_date, prev_capital: dict, current_capital: dict) -> str:
    """Формирует отчёт о росте капитала между двумя датами."""
    prev_month_name = format_ru_month_label(prev_date)
    current_month_name = format_ru_month_label(current_date)

    rub_growth = current_capital.get('RUB', 0) - prev_capital.get('RUB', 0)
    usd_growth = current_capital.get('USD', 0) - prev_capital.get('USD', 0)

    rub_growth_percent = (rub_growth / prev_capital['RUB'] * 100) if prev_capital.get('RUB', 0) > 0 else 0
    usd_growth_percent = (usd_growth / prev_capital['USD'] * 100) if prev_capital.get('USD', 0) > 0 else 0

    growth_emoji_rub = "📈" if rub_growth >= 0 else "📉"
    growth_emoji_usd = "📈" if usd_growth >= 0 else "📉"

    lines = [
        "📊 Динамика капитала по месяцам:",
        "",
        "🇷🇺 RUB:",
        f"  {prev_month_name}: {fmt_money_str(str(prev_capital.get('RUB', 0)))}",
        f"  {current_month_name}: {fmt_money_str(str(current_capital.get('RUB', 0)))}",
        f"  {growth_emoji_rub} {fmt_money_str(str(rub_growth))} ({rub_growth_percent:+.1f}%)",
        "",
        "🇺🇸 USD:",
        f"  {prev_month_name}: {fmt_money_str(str(prev_capital.get('USD', 0)))}",
        f"  {current_month_name}: {fmt_money_str(str(current_capital.get('USD', 0)))}",
        f"  {growth_emoji_usd} {fmt_money_str(str(usd_growth))} ({usd_growth_percent:+.1f}%)",
    ]
    return "\n".join(lines)


def report_asset_snapshot_created(capital: dict) -> str:
    """Формирует сообщение об успешном создании снэпшота и текущем капитале."""
    return "\n".join([
        "📸 Снэпшот капитала создан!",
        "",
        f"📊 Текущий капитал:",
        f"• 🇷🇺 {fmt_money_str(str(capital.get('RUB', 0)))} RUB",
        f"• 🇺🇸 {fmt_money_str(str(capital.get('USD', 0)))} USD",
        "",
        "💡 Снэпшоты помогают корректно анализировать динамику капитала.",
    ])


def report_assets_detailed_list(assets_by_currency: dict, total_usd: float, total_rub: float, updated_at, unknown_currencies: set[str] | None = None) -> str:
    """Формирует детальный список активов и общие итоги.

    Визуально группирует по категориям, внутри выводит позиции как "<amount> <currency>".
    assets_by_currency: { currency: [AssetLatestValues, ...] }
    updated_at: datetime | str | None
    """
    parts = ["💼 <b>Детальный список активов:</b>\n"]

    unknown_currencies = unknown_currencies or set()

    # Перегруппируем: категория -> [(amount, currency_code)]
    categories: dict[str, list[tuple[float, str]]] = {}
    for currency, currency_assets in assets_by_currency.items():
        for asset in currency_assets:
            category = asset.category_name or "Без категории"
            categories.setdefault(category, []).append((float(asset.amount), currency))

    # Приоритетный порядок вывода категорий, остальные по алфавиту
    preferred = ["Акции", "Вклад", "Инвесткопилка", "Крипта"]
    ordered_categories = [c for c in preferred if c in categories] + sorted(
        [c for c in categories.keys() if c not in preferred]
    )

    icon_by_category = {
        "акции": "📈",
        "вклад": "🏦",
        "инвесткопилка": "💰",
        "крипта": "🪙",
        "кэш": "💵",
    }

    for category in ordered_categories:
        icon = icon_by_category.get(category.strip().lower(), "🗂️")
        parts.append(f"{icon} <b>{category}:</b>")
        for amount, currency in categories[category]:
            # Форматируем сумму: для криптовалют используем спец-формат, иначе денежный
            if currency in ["BTC", "ETH", "SOL", "USDT", "USDC", "TRX"]:
                amt_str = fmt_crypto_str(str(amount), currency)
            else:
                amt_str = fmt_money_str(str(amount))

            suffix = " (валюта не распознана)" if currency in unknown_currencies else ""
            parts.append(f"  {amt_str} {currency}{suffix}")
        parts.append("")

    parts.extend([
        "📊 <b>Общие итоги:</b>",
        f"• 🇺🇸 <b>USD:</b> {fmt_money_str(str(total_usd))}",
        f"• 🇷🇺 <b>RUB:</b> {fmt_money_str(str(total_rub))}",
        "",
        f"📅 <b>Обновлено:</b> {updated_at.strftime('%d.%m.%Y %H:%M') if hasattr(updated_at, 'strftime') else (updated_at or 'Неизвестно')}",
    ])

    return "\n".join(parts)


def report_asset_no_history(current_capital: dict) -> str:
    """Сообщение, когда текущий капитал есть, а исторических данных ещё нет."""
    return "\n".join([
        "📊 Текущий капитал:",
        f"• 🇷🇺 {fmt_money_str(str(current_capital.get('RUB', 0)))} RUB",
        f"• 🇺🇸 {fmt_money_str(str(current_capital.get('USD', 0)))} USD",
        "",
        "Исторических данных для сравнения пока нет.",
    ])
