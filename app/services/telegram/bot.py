"""Aiogram 3 bot: handles /start <token>, /today, /yesterday, /help, /unlink.

Runs as a separate long-polling worker (see app/bot/__main__.py). Each handler
opens its own AsyncSession, mirroring the FastAPI side.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.report import ReportPeriod
from app.models.user import User
from app.models.user_restaurant_role import UserRestaurantRole
from app.repositories.report_repo import ReportRepository
from app.repositories.restaurant_repo import RestaurantRepository
from app.services.telegram.formatter import (
    render_daily_digest,
    render_help,
    render_link_success,
    render_link_token_invalid,
    render_not_linked,
    render_unlinked,
)
from app.services.telegram.link_service import TelegramLinkService
from app.services.telegram.notifier import dashboard_url, fetch_top_recommendations

logger = get_logger("telegram.bot")
router = Router(name="margin")


# ---------- helpers ----------


async def _with_session(fn: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async with AsyncSessionLocal() as session:
        await fn(session)


async def _resolve_user_by_chat(session: AsyncSession, chat_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_chat_id == chat_id))


async def _list_user_restaurants(session: AsyncSession, user: User) -> list[tuple[uuid.UUID, str]]:
    rows = await session.execute(
        select(UserRestaurantRole.restaurant_id)
        .where(UserRestaurantRole.user_id == user.id)
    )
    rids = [r[0] for r in rows.all()]
    if not rids:
        return []
    restaurants = []
    repo = RestaurantRepository(session)
    for rid in rids:
        r = await repo.get(rid)
        if r and r.is_active:
            restaurants.append((r.id, r.name))
    return restaurants


def _restaurant_choice_markup(
    restaurants: list[tuple[uuid.UUID, str]], action: str
) -> InlineKeyboardMarkup:
    """Action ∈ {today, yesterday}."""
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"r:{action}:{rid}")]
        for rid, name in restaurants
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- handlers ----------


@router.message(CommandStart(deep_link=True))
async def on_start_with_token(message: Message, command: CommandObject) -> None:
    token = (command.args or "").strip()
    if not token or message.from_user is None:
        await message.answer(render_link_token_invalid())
        return

    async def _job(session: AsyncSession) -> None:
        try:
            user = await TelegramLinkService(session).consume(
                token,
                chat_id=message.chat.id,
                telegram_username=message.from_user.username if message.from_user else None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram.link.failed", error=str(exc))
            await message.answer(render_link_token_invalid())
            return
        await message.answer(render_link_success(user.full_name))

    await _with_session(_job)


@router.message(CommandStart())
async def on_start_plain(message: Message) -> None:
    async def _job(session: AsyncSession) -> None:
        user = await _resolve_user_by_chat(session, message.chat.id)
        if not user:
            await message.answer(render_not_linked())
            return
        await message.answer(render_help())

    await _with_session(_job)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(render_help())


@router.message(Command("unlink"))
async def on_unlink(message: Message) -> None:
    async def _job(session: AsyncSession) -> None:
        user = await _resolve_user_by_chat(session, message.chat.id)
        if not user:
            await message.answer(render_not_linked())
            return
        await TelegramLinkService(session).unlink(user)
        await message.answer(render_unlinked())

    await _with_session(_job)


@router.message(Command("today"))
async def on_today(message: Message) -> None:
    await _send_report_for_day(message, date.today())


@router.message(Command("yesterday"))
async def on_yesterday(message: Message) -> None:
    await _send_report_for_day(message, date.today() - timedelta(days=1))


async def _send_report_for_day(message: Message, day: date) -> None:
    async def _job(session: AsyncSession) -> None:
        user = await _resolve_user_by_chat(session, message.chat.id)
        if not user:
            await message.answer(render_not_linked())
            return
        restaurants = await _list_user_restaurants(session, user)
        if not restaurants:
            await message.answer("Нет доступных ресторанов.")
            return
        if len(restaurants) == 1:
            await _reply_with_report(session, message, restaurants[0][0], day)
            return
        action = "today" if day == date.today() else "yesterday"
        await message.answer(
            "Выбери ресторан:",
            reply_markup=_restaurant_choice_markup(restaurants, action),
        )

    await _with_session(_job)


@router.callback_query(F.data.startswith("r:"))
async def on_restaurant_choice(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Неизвестная команда", show_alert=False)
        return
    _, action, rid_str = parts
    try:
        rid = uuid.UUID(rid_str)
    except ValueError:
        await callback.answer("Некорректный id", show_alert=False)
        return
    day = date.today() if action == "today" else date.today() - timedelta(days=1)

    async def _job(session: AsyncSession) -> None:
        if not callback.message:
            return
        await _reply_with_report(session, callback.message, rid, day)
        await callback.answer()

    await _with_session(_job)


async def _reply_with_report(
    session: AsyncSession, message: Message, restaurant_id: uuid.UUID, day: date
) -> None:
    restaurant = await RestaurantRepository(session).get(restaurant_id)
    if not restaurant:
        await message.answer("Ресторан не найден.")
        return
    report = await ReportRepository(session).get(
        restaurant_id, ReportPeriod.DAILY, day
    )
    if not report:
        await message.answer(
            f"Отчёт за {day.strftime('%d.%m.%Y')} ещё не готов. "
            "Подожди немного после закрытия смены или собери его вручную в кабинете."
        )
        return
    recs = await fetch_top_recommendations(session, restaurant_id, day, limit=3)
    text = render_daily_digest(
        restaurant.name,
        day,
        report,
        recs,
        currency=restaurant.currency,
        dashboard_url=dashboard_url(restaurant_id),
    )
    await message.answer(text)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


def build_bot() -> Bot:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
