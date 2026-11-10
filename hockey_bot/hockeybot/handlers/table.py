from __future__ import annotations

import asyncio
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile

from hockeybot.captions import split_caption
from hockeybot.db import Database
from hockeybot.keyboards import table_done_kb, table_kb
from hockeybot.khl import KhlError
from hockeybot.poster import PosterError, render_table
from hockeybot.standings import MSK, apply_movement, load_standings, snapshot_rows

router = Router(name="table")

_PROMPT = (
    "Турнирная таблица КХЛ.\n\n"
    "Запад и Восток — текущий регулярный чемпионат. "
    "У места стрелка, у очков прибавка: сравнение с таблицей прошлого дня, которую бот уже собирал. "
    "В первый день стрелок ещё нет. Можно взять одну конференцию или таблицу прошлого сезона."
)


@router.callback_query(F.data == "menu:table")
async def ask_table(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await callback.answer()
    await callback.message.answer(_PROMPT, reply_markup=table_kb())


@router.callback_query(F.data.startswith("table:"))
async def build_table(callback: CallbackQuery, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    scope = callback.data.split(":", 1)[1]
    await callback.answer()
    await callback.message.answer("Собираю таблицу…")
    try:
        board = await asyncio.to_thread(load_standings, scope)
    except KhlError as exc:
        await callback.message.answer(str(exc), reply_markup=table_kb())
        return
    if scope != "previous":
        day = datetime.now(MSK).date().isoformat()
        board = apply_movement(board, db.previous_table(board.season, day))
        db.save_table_snapshot(board.season, day, snapshot_rows(board))
    user_id = callback.from_user.id
    dest = db.path.parent / "renders" / f"table-{user_id}-{int(time.time())}.png"
    try:
        await asyncio.to_thread(render_table, board, dest, chrome_path)
    except PosterError as exc:
        await callback.message.answer(str(exc))
        return
    post = {"path": str(dest), "caption": board.caption, "kind": "table"}
    await state.set_state(None)
    await state.update_data(last_post=post)
    settings = db.settings(user_id)
    markup = table_done_kb(has_channel=bool(settings.channel_id))
    main_caption, rest = split_caption(board.caption)
    await callback.message.answer_photo(FSInputFile(dest), caption=main_caption or None, reply_markup=None if rest else markup)
    if rest:
        await callback.message.answer(rest, reply_markup=markup)
