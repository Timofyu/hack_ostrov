from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from hockeybot.captions import split_caption
from hockeybot.daypreview import load_day
from hockeybot.db import Database
from hockeybot.keyboards import create_post_kb, day_done_kb, day_kb
from hockeybot.khl import KhlError, looks_like_khl_request, parse_calendar_day
from hockeybot.poster import PosterError, render_day
from hockeybot.states import DaySG

router = Router(name="day")

MSK = timezone(timedelta(hours=3))

_PROMPT = (
    "Превью дня\n\n"
    "Напиши дату: 8 ноября или 08.11.2026.\n"
    "Можно нажать «Сегодня» или «Завтра»."
)


@router.callback_query(F.data == "menu:create")
async def choose_kind(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await callback.answer()
    await callback.message.answer("Какой пост?", reply_markup=create_post_kb())


@router.callback_query(F.data == "menu:day")
async def ask_day(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DaySG.date)
    await callback.answer()
    await callback.message.answer(_PROMPT, reply_markup=day_kb())


@router.callback_query(F.data == "day:today")
async def day_today(callback: CallbackQuery, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    await callback.answer()
    await _build(callback.message, state, db, chrome_path, datetime.now(MSK).date(), callback.from_user.id)


@router.callback_query(F.data == "day:tomorrow")
async def day_tomorrow(callback: CallbackQuery, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    await callback.answer()
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    await _build(callback.message, state, db, chrome_path, tomorrow, callback.from_user.id)


@router.message(DaySG.date, F.text, ~F.text.startswith("/"))
async def day_text(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    text = message.text or ""
    if looks_like_khl_request(text) and not _date_only(text):
        from hockeybot.handlers.match import import_from_khl

        await import_from_khl(message, state, db, chrome_path)
        return
    try:
        day = parse_calendar_day(text, today=datetime.now(MSK).date())
    except KhlError as exc:
        await message.answer(str(exc), reply_markup=day_kb())
        return
    user_id = message.from_user.id if message.from_user else message.chat.id
    await _build(message, state, db, chrome_path, day, user_id)


def _date_only(text: str) -> bool:
    try:
        parse_calendar_day(text, today=datetime.now(MSK).date())
    except KhlError:
        return False
    return True


async def _build(message: Message, state: FSMContext, db: Database, chrome_path: str | None, day, user_id: int) -> None:
    await message.answer("Собираю превью дня…")
    try:
        slate = await asyncio.to_thread(load_day, day)
    except KhlError as exc:
        await message.answer(str(exc), reply_markup=day_kb())
        return
    dest = db.path.parent / "renders" / f"day-{user_id}-{int(time.time())}.png"
    try:
        await asyncio.to_thread(render_day, slate, dest, chrome_path)
    except PosterError as exc:
        await message.answer(str(exc))
        return
    await state.set_state(None)
    await state.update_data(last_post={"path": str(dest), "caption": slate.caption, "kind": "day"})
    settings = db.settings(user_id)
    markup = day_done_kb(has_channel=bool(settings.channel_id))
    main_caption, rest = split_caption(slate.caption)
    await message.answer_photo(FSInputFile(dest), caption=main_caption or None, reply_markup=None if rest else markup)
    if rest:
        await message.answer(rest, reply_markup=markup)
