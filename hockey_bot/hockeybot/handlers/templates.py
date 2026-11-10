from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from hockeybot.captions import render_caption
from hockeybot.catalog import all_templates, resolve_template
from hockeybot.db import Database
from hockeybot.handlers.common import placeholder_help
from hockeybot.keyboards import (
    confirm_delete_kb,
    keep_text_kb,
    kind_kb,
    menu_kb,
    template_card_kb,
    template_list_kb,
)
from hockeybot.states import TemplateSG
from hockeybot.templates_lib import demo_context

router = Router(name="templates")


@router.message(Command("templates"))
@router.callback_query(F.data == "menu:templates")
async def show_templates(event: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.set_state(None)
    message = event.message if isinstance(event, CallbackQuery) else event
    user_id = event.from_user.id
    if isinstance(event, CallbackQuery):
        await event.answer()
    settings = db.settings(user_id)
    templates = all_templates(db, user_id)
    await message.answer(
        "Шаблоны постов. Основной подставляется в новый матч.",
        reply_markup=template_list_kb(templates, settings.default_template),
    )


@router.callback_query(F.data.startswith("topen|"))
async def open_template(callback: CallbackQuery, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    template = resolve_template(db, callback.from_user.id, template_id)
    if template.id != template_id:
        await callback.answer("Шаблон не найден", show_alert=True)
        return
    kind = "анонс" if template.kind == "announce" else "итог"
    origin = "встроенный" if template.builtin else "свой"
    preview = render_caption(template.body, demo_context())
    await callback.answer()
    await callback.message.answer(
        f"{template.name}\n{origin}, {kind}\n\nТак выглядит на примере Салават — Лада:\n\n{preview}",
        reply_markup=template_card_kb(template),
    )


@router.callback_query(F.data.startswith("tdef|"))
async def make_default(callback: CallbackQuery, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    template = resolve_template(db, callback.from_user.id, template_id)
    if template.id != template_id:
        await callback.answer("Шаблон не найден", show_alert=True)
        return
    db.set_default_template(callback.from_user.id, template.id)
    await callback.answer("Теперь это основной")
    await callback.message.answer(f"Основной шаблон — {template.name}.", reply_markup=menu_kb())


@router.callback_query(F.data == "tnew")
async def new_template(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TemplateSG.name)
    await state.update_data(draft_kind=None, draft_body=None)
    await callback.answer()
    await callback.message.answer("Как назвать шаблон?")


@router.callback_query(F.data.startswith("tcopy|"))
async def copy_template(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    template = resolve_template(db, callback.from_user.id, template_id)
    await state.set_state(TemplateSG.name)
    await state.update_data(draft_kind=template.kind, draft_body=template.body)
    await callback.answer()
    await callback.message.answer(
        f"Копирую «{template.name}». Как назвать новый шаблон?"
    )


@router.message(TemplateSG.name, F.text, ~F.text.startswith("/"))
async def template_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if not 2 <= len(name) <= 40:
        await message.answer("Имя нужно от 2 до 40 знаков.")
        return
    data = await state.get_data()
    await state.update_data(draft_name=name)
    if data.get("draft_body"):
        await state.set_state(TemplateSG.body)
        await message.answer(
            "Текст шаблона. Можешь прислать свой или оставить текущий.\n\n"
            f"{data['draft_body']}\n\n{placeholder_help()}",
            reply_markup=keep_text_kb(),
        )
        return
    await state.set_state(TemplateSG.kind)
    await message.answer("Это итог сыгранного матча или анонс?", reply_markup=kind_kb())


@router.callback_query(TemplateSG.kind, F.data.startswith("tkind|"))
async def template_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split("|", 1)[1]
    if kind not in {"result", "announce"}:
        await callback.answer()
        return
    await state.update_data(draft_kind=kind)
    await state.set_state(TemplateSG.body)
    await callback.answer()
    await callback.message.answer("Пришли текст шаблона.\n\n" + placeholder_help())


@router.callback_query(TemplateSG.body, F.data == "tkeep")
async def keep_template_text(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    body = (data.get("draft_body") or "").strip()
    if not body:
        await callback.answer("Текста ещё нет", show_alert=True)
        return
    await callback.answer()
    await _save_template(callback.message, state, db, callback.from_user.id, body)


@router.message(TemplateSG.body, F.text, ~F.text.startswith("/"))
async def template_body(message: Message, state: FSMContext, db: Database) -> None:
    body = (message.text or "").strip()
    if not 2 <= len(body) <= 1500:
        await message.answer("Текст шаблона — от 2 до 1500 знаков.")
        return
    await _save_template(message, state, db, message.from_user.id, body)


@router.callback_query(F.data.startswith("tedit|"))
async def edit_template(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    template = db.get_template(callback.from_user.id, template_id)
    if template is None:
        await callback.answer("Это встроенный шаблон. Его можно скопировать.", show_alert=True)
        return
    await state.set_state(TemplateSG.edit_body)
    await state.update_data(edit_id=template.id)
    await callback.answer()
    await callback.message.answer(
        f"Новый текст для «{template.name}».\n\nСейчас так:\n{template.body}\n\n{placeholder_help()}"
    )


@router.message(TemplateSG.edit_body, F.text, ~F.text.startswith("/"))
async def save_edit(message: Message, state: FSMContext, db: Database) -> None:
    body = (message.text or "").strip()
    if not 2 <= len(body) <= 1500:
        await message.answer("Текст шаблона — от 2 до 1500 знаков.")
        return
    data = await state.get_data()
    template_id = data.get("edit_id", "")
    if not db.update_body(message.from_user.id, template_id, body):
        await message.answer("Шаблон не найден.", reply_markup=menu_kb())
        await state.set_state(None)
        return
    await state.set_state(None)
    preview = render_caption(body, demo_context())
    await message.answer(f"Обновил.\n\nПример:\n\n{preview}", reply_markup=menu_kb())


@router.callback_query(F.data.startswith("tdel|"))
async def ask_delete(callback: CallbackQuery, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    template = db.get_template(callback.from_user.id, template_id)
    if template is None:
        await callback.answer("Встроенный шаблон не удаляется", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        f"Удалить шаблон «{template.name}»?",
        reply_markup=confirm_delete_kb(template.id),
    )


@router.callback_query(F.data.startswith("tdelyes|"))
async def delete_template(callback: CallbackQuery, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    owner = callback.from_user.id
    if not db.delete_template(owner, template_id):
        await callback.answer("Уже удалён", show_alert=True)
        return
    if db.settings(owner).default_template == template_id:
        db.set_default_template(owner, "builtin:result")
    await callback.answer("Удалил")
    templates = all_templates(db, owner)
    await callback.message.answer(
        "Шаблон удалён.",
        reply_markup=template_list_kb(templates, db.settings(owner).default_template),
    )


@router.callback_query(F.data == "ttournament")
async def ask_tournament(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    current = db.settings(callback.from_user.id).tournament
    await state.set_state(TemplateSG.tournament)
    await callback.answer()
    await callback.message.answer(
        f"Что писать в углу превью вместо «{current}»?\nНапример: КХЛ · 26/27"
    )


@router.message(TemplateSG.tournament, F.text, ~F.text.startswith("/"))
async def save_tournament(message: Message, state: FSMContext, db: Database) -> None:
    text = " ".join((message.text or "").split())
    if not 2 <= len(text) <= 32:
        await message.answer("Надпись нужна от 2 до 32 знаков.")
        return
    db.set_tournament(message.from_user.id, text)
    await state.set_state(None)
    await message.answer(f"На превью теперь «{text}».", reply_markup=menu_kb())


async def _save_template(message: Message, state: FSMContext, db: Database, owner_id: int, body: str) -> None:
    data = await state.get_data()
    name = data.get("draft_name") or "Шаблон"
    kind = data.get("draft_kind") or "result"
    template = db.add_template(owner_id, name, kind, body)
    await state.set_state(None)
    preview = render_caption(body, demo_context())
    await message.answer(
        f"Сохранил «{template.name}».\n\nПример:\n\n{preview}",
        reply_markup=menu_kb(),
    )
