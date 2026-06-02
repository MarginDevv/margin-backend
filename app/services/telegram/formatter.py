"""HTML message templates for Telegram digests.

Telegram parse_mode=HTML supports: <b>, <i>, <u>, <s>, <code>, <pre>, <a>.
We render messages in Russian since this is the primary product locale.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.recommendation import Recommendation, RecommendationPriority
from app.models.report import Report

PRIORITY_LABEL = {
    RecommendationPriority.LOW: "▫️",
    RecommendationPriority.MEDIUM: "🔹",
    RecommendationPriority.HIGH: "🔸",
    RecommendationPriority.CRITICAL: "🔴",
}


def _money(value: Decimal | float, currency: str = "₽") -> str:
    return f"{Decimal(value):,.0f} {currency}".replace(",", " ")


def _pct(value: Decimal | float) -> str:
    return f"{float(value):.1f}%"


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_daily_digest(
    restaurant_name: str,
    for_date: date,
    report: Report,
    top_recommendations: list[Recommendation],
    *,
    currency: str = "₽",
    dashboard_url: str | None = None,
) -> str:
    name = escape_html(restaurant_name)
    lines: list[str] = []
    lines.append(f"📊 <b>Margin · отчёт за {for_date.strftime('%d.%m.%Y')}</b>")
    lines.append(f"🏢 {name}")
    lines.append("")
    lines.append(f"Выручка: <b>{_money(report.net_revenue, currency)}</b>")
    lines.append(
        f"Прибыль: <b>{_money(report.profit, currency)}</b>"
        f" · маржа {_pct(report.margin_percent)}"
    )
    lines.append(
        f"Чеков: <b>{report.orders_count}</b> · средний чек {_money(report.avg_check, currency)}"
    )
    if report.guests_count:
        lines.append(f"Гостей: {report.guests_count}")
    lines.append("")
    if top_recommendations:
        lines.append("💡 <b>Топ рекомендации:</b>")
        for i, rec in enumerate(top_recommendations, 1):
            icon = PRIORITY_LABEL.get(rec.priority, "•")
            lines.append(f"{i}. {icon} <b>{escape_html(rec.title)}</b>")
            if rec.action:
                lines.append(f"   → {escape_html(rec.action)}")
            if rec.estimated_uplift:
                lines.append(f"   <i>оценка эффекта: {_money(rec.estimated_uplift, currency)}</i>")
        lines.append("")
    if dashboard_url:
        lines.append(f"📱 Подробнее в кабинете: {dashboard_url}")
    return "\n".join(lines)


def render_link_success(user_full_name: str | None) -> str:
    name = escape_html(user_full_name) if user_full_name else "друг"
    return (
        f"✅ Готово, {name}!\n"
        "Аккаунт Margin привязан. Я буду присылать ежедневный отчёт и рекомендации "
        "сразу после закрытия смены ресторана.\n\n"
        "Команды: /today, /yesterday, /help, /unlink"
    )


def render_help() -> str:
    return (
        "<b>Margin Bot</b>\n\n"
        "Я ИИ-управляющий для ресторанов. После закрытия смены пришлю отчёт "
        "и рекомендации по росту прибыли.\n\n"
        "<b>Команды</b>\n"
        "/today — отчёт за сегодня\n"
        "/yesterday — отчёт за вчера\n"
        "/help — эта справка\n"
        "/unlink — отвязать аккаунт"
    )


def render_link_token_invalid() -> str:
    return (
        "❌ Ссылка для привязки недействительна или истекла.\n"
        "Открой кабинет Margin и сгенерируй новую."
    )


def render_not_linked() -> str:
    return (
        "Этот Telegram-аккаунт ещё не привязан к Margin.\n"
        "Открой кабинет и нажми <b>«Подключить Telegram»</b>."
    )


def render_unlinked() -> str:
    return "Готово, аккаунт отвязан. Чтобы снова получать отчёты — привяжи заново в кабинете."
