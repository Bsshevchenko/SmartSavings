from app.utils.formatting import fmt_money_str


def report_for_expense(label: str, totals: dict) -> str:
    """Формирует текстовый отчёт о расходах для пользователя."""
    return "\n".join([
        f"📅 {label}:",
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
