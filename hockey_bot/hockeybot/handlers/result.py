from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from hockeybot.captions import render_caption
from hockeybot.catalog import active_result_template
from hockeybot.db import Database
from hockeybot.handlers.common import placeholder_help
from hockeybot.keyboards import menu_kb, result_kb
from hockeybot.khl import looks_like_khl_request
from hockeybot.states import ResultSG
from hockeybot.templates_lib import demo_context, template_body_ok

router = Router(name="result")


def result_intro(db: Database, user_id: int) -> str:
    template = active_result_template(db, user_id)
    sample = demo_context()
    sample["url"] = "https://www.khl.ru/game/…"
    preview = render_caption(template.body, sample)
    if len(preview) > 500:
        preview = preview[:500].rstrip() + "…"
    return (
        "Итоги матча\n\n"
        f"Пост собирается по шаблону «{template.name}»:\n\n"
        f"{preview}\n\n"
        "Пришли свой шаблон, если нужна другая структура. "
        "В тексте должны быть поля вроде {home}, {score}, {goals_block}. "
        "Потом напиши встречу: Авангард ЦСКА 5 ноября 2026.\n\n"
        "Если матч ещё идёт, пост придёт сам, когда КХЛ закроет протокол. "
        "Если сайта долго нет — собери пост вручную."
    )


async def open_results(message: Message, state: FSMContext, db: Database, user_id: int) -> None:
    await state.set_state(None)
    await message.answer(result_intro(db, user_id), reply_markup=result_kb())


@router.message(Command("match"))
async def start_match_message(message: Message, state: FSMContext, db: Database) -> None:
    await open_results(message, state, db, message.from_user.id)


@router.callback_query(F.data == "menu:match")
async def start_match_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    await open_results(callback.message, state, db, callback.from_user.id)


@router.callback_query(F.data == "result:template")
async def ask_template(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ResultSG.template)
    await callback.answer()
    await callback.message.answer(
        "Пришли текст шаблона для итогов.\n\n"
        "Например:\n"
        "{home} — {away}\n"
        "{score}\n"
        "{when}\n"
        "\n"
        "{goals_block}\n"
        "\n"
        "{url}\n\n"
        + placeholder_help(),
        reply_markup=result_kb(),
    )


@router.message(ResultSG.template, F.text, ~F.text.startswith("/"))
async def save_template(message: Message, state: FSMContext, db: Database) -> None:
    body = (message.text or "").strip()
    problem = template_body_ok(body)
    if problem:
        await message.answer(f"{problem}\n\n{placeholder_help()}")
        return
    saved = db.save_result_template(message.from_user.id, body)
    await state.set_state(ResultSG.query)
    await message.answer(
        f"Шаблон «{saved.name}» сохранён и стал основным.\n\n"
        "Теперь напиши встречу и дату:\n"
        "Авангард ЦСКА 5 ноября 2026",
        reply_markup=result_kb(),
    )


@router.callback_query(F.data == "result:query")
async def ask_query(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ResultSG.query)
    await callback.answer()
    await callback.message.answer(
        "Напиши два клуба и дату одной строкой:\n"
        "Авангард ЦСКА 5 ноября 2026\n"
        "Локомотив Ак Барс 21 мая 2026\n\n"
        "Если матч уже закончился, сразу соберу пост. "
        "Если ещё идёт — пришлю его, когда протокол закроется.",
        reply_markup=result_kb(),
    )


@router.message(ResultSG.query, F.text, ~F.text.startswith("/"))
async def on_query(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    text = message.text or ""
    if not looks_like_khl_request(text):
        await message.answer("Нужны два клуба и дата: Авангард ЦСКА 5 ноября 2026")
        return
    from hockeybot.handlers.match import import_from_khl

    await import_from_khl(message, state, db, chrome_path)


@router.callback_query(F.data == "watch:stop")
async def stop_watch(callback: CallbackQuery, db: Database) -> None:
    stopped = db.stop_watches(callback.from_user.id)
    await callback.answer()
    text = "Больше не слежу за протоколом." if stopped else "Слежки не было."
    await callback.message.answer(text, reply_markup=menu_kb())
