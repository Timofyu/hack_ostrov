from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, FSInputFile, Message

from hockeybot.captions import build_context, render_caption, split_caption
from hockeybot.khl import KhlError, load_match, looks_like_khl_request
from hockeybot.catalog import all_templates, resolve_template
from hockeybot.db import Database
from hockeybot.keyboards import (
    announce_steps,
    clubs_kb,
    done_kb,
    menu_kb,
    result_steps,
    text_choice_kb,
    wizard_kb,
)
from hockeybot.models import Club, Footer, Goal, MatchCard
from hockeybot.parsing import ParseError, parse_footer, parse_goals, parse_periods, parse_quick, parse_score, parse_when
from hockeybot.photos import download_match_photo
from hockeybot.poster import PosterError, render_poster
from hockeybot.social import find_social_photos
from hockeybot.states import MatchSG
from hockeybot.teams import custom_club, find_clubs, resolve_club

router = Router(name="match")

_PROMPTS = {
    MatchSG.home: (
        "Встреча с сайта КХЛ\n\n"
        "Напиши два клуба и дату одной строкой:\n"
        "Авангард ЦСКА 5 ноября 2026\n"
        "Локомотив Ак Барс 21 мая 2026\n\n"
        "Бот откроет протокол на khl.ru, в том числе плей-офф прошлого сезона, "
        "возьмёт фото из телеграм-канала клуба и соберёт картинку с текстом.\n"
        "Порядок клубов любой: хозяев он возьмёт из протокола.\n\n"
        "Если хочешь собрать пост вручную, напиши только хозяев. Например: Салават Юлаев"
    ),
    MatchSG.away: "Гости\n\nНапример: Лада",
    MatchSG.score: "Счёт\n\nФормат 5:0 — сначала шайбы хозяев.",
    MatchSG.when: "Дата и арена\n\nОдним сообщением: 4 ноября · Уфа-Арена",
    MatchSG.periods: "Периоды\n\nНапример: 2:0, 1:0, 2:0",
    MatchSG.goals: (
        "Шайбы\n\nКаждая с новой строки:\n"
        "03:33 Родуолд — Кулик, Ремпал\n"
        "50:14 Ремпал — Родуолд | мен\n"
        "55:43 Ремпал — Жаровский, Цулыгин | бол"
    ),
    MatchSG.footer: (
        "Нижняя плашка\n\nДо трёх частей через вертикальную черту:\n"
        "Бочаров | 33 сейва | Шатаут\n\n"
        "Вторая строка — подписи мельче:\n"
        "33-й в карьере | | первый в сезоне"
    ),
    MatchSG.note: (
        "Сноска\n\nКороткая строка под протоколом. Например:\n"
        "Серия из трёх поражений прервана"
    ),
    MatchSG.photo: "Фото\n\nПришли кадр с матча. Без фото соберу превью из типографики.",
    MatchSG.quick: (
        "Одним сообщением\n\n"
        "Салават Юлаев — Лада\n"
        "5:0\n"
        "4 ноября · Уфа-Арена\n"
        "2:0, 1:0, 2:0\n\n"
        "03:33 Родуолд — Кулик, Ремпал\n"
        "50:14 Ремпал — Родуолд | мен\n\n"
        "Бочаров | 33 сейва | Шатаут\n"
        "33-й в карьере | | первый в сезоне\n\n"
        "Серия из трёх поражений прервана"
    ),
}


def flow(kind: str) -> list[State]:
    return announce_steps() if kind == "announce" else result_steps()


async def begin_match(message: Message, state: FSMContext, db: Database, user_id: int) -> None:
    settings = db.settings(user_id)
    template = resolve_template(db, user_id, settings.default_template)
    last_post = (await state.get_data()).get("last_post")
    await state.clear()
    await state.update_data(
        last_post=last_post,
        template_id=template.id,
        template_name=template.name,
        kind=template.kind,
        tournament=settings.tournament,
    )
    await state.set_state(MatchSG.home)
    await send_prompt(message, state, MatchSG.home)


@router.message(Command("match"))
async def start_match_message(message: Message, state: FSMContext, db: Database) -> None:
    await begin_match(message, state, db, message.from_user.id)


@router.callback_query(F.data == "menu:match")
async def start_match_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    await begin_match(callback.message, state, db, callback.from_user.id)


@router.callback_query(F.data == "wiz:quick")
async def to_quick(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MatchSG.quick)
    await callback.answer()
    await send_prompt(callback.message, state, MatchSG.quick)


@router.callback_query(F.data == "wiz:skip")
async def skip_step(callback: CallbackQuery, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    current = await _current(state)
    await callback.answer()
    if current is None:
        return
    await _clear_step(state, current)
    await go_next(callback.message, state, current, db, chrome_path)


@router.callback_query(F.data == "wiz:back")
async def back_step(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    current_name = await state.get_state()
    if current_name == MatchSG.quick.state:
        await state.set_state(MatchSG.home)
        await callback.answer()
        await send_prompt(callback.message, state, MatchSG.home)
        return
    steps = flow(data.get("kind", "result"))
    names = [step.state for step in steps]
    if current_name not in names or names.index(current_name) == 0:
        await state.clear()
        await callback.answer()
        await callback.message.answer("Остановил.", reply_markup=menu_kb())
        return
    previous = steps[names.index(current_name) - 1]
    await state.set_state(previous)
    await callback.answer()
    await send_prompt(callback.message, state, previous)


@router.callback_query(F.data.startswith("club:"))
async def pick_club(callback: CallbackQuery, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    data = await state.get_data()
    choices = data.get("club_choices") or []
    try:
        index = int(callback.data.split(":", 1)[1])
        club = Club.from_dict(choices[index])
    except (IndexError, ValueError, KeyError):
        await callback.answer("Список устарел, пришли имя ещё раз", show_alert=True)
        return
    slot = data.get("club_slot", "home")
    await state.update_data(**{slot: club.to_dict()})
    await callback.answer(club.name)
    current = await _current(state)
    if current is None:
        return
    await go_next(callback.message, state, current, db, chrome_path)


@router.message(MatchSG.quick, F.text, ~F.text.startswith("/"))
async def on_quick(message: Message, state: FSMContext) -> None:
    try:
        parsed = parse_quick(message.text or "")
        home = _require_known_or_custom(parsed["home_name"], "home")
        away = _require_known_or_custom(parsed["away_name"], "away")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(
        home=home.to_dict(),
        away=away.to_dict(),
        home_score=parsed["home_score"],
        away_score=parsed["away_score"],
        date=parsed["date"],
        arena=parsed["arena"],
        periods=parsed["periods"],
        goals=[asdict(goal) for goal in parsed["goals"]],
        footer=parsed["footer"].to_dict(),
        note=parsed["note"],
        photo_path=None,
    )
    await state.set_state(MatchSG.photo)
    await message.answer("Матч разобрал. Осталось фото — или пропусти.")
    await send_prompt(message, state, MatchSG.photo)


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def khl_from_menu(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    text = message.text or ""
    if not looks_like_khl_request(text):
        await message.answer(
            "Выбери в меню пост о матче или турнирную таблицу.\n"
            "Матч можно прислать и так: Авангард ЦСКА 5 ноября 2026",
            reply_markup=menu_kb(),
        )
        return
    await import_from_khl(message, state, db, chrome_path)


@router.message(MatchSG.home, F.text, ~F.text.startswith("/"))
@router.message(MatchSG.away, F.text, ~F.text.startswith("/"))
async def on_club(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    current = await _current(state)
    if current == MatchSG.home and looks_like_khl_request(message.text or ""):
        await import_from_khl(message, state, db, chrome_path)
        return
    slot = "home" if current == MatchSG.home else "away"
    raw = " ".join((message.text or "").split())
    if len(raw) < 2:
        await message.answer("Имя клуба слишком короткое.")
        return
    if len(raw) > 48:
        await message.answer("Имя клуба длиннее 48 знаков.")
        return
    hits = find_clubs(raw)
    if len(hits) > 1:
        await state.update_data(club_choices=[club.to_dict() for club in hits], club_slot=slot)
        await message.answer("Несколько клубов. Выбери или пришли имя точнее.", reply_markup=clubs_kb(hits))
        return
    if len(hits) == 1:
        club = hits[0]
    else:
        club = custom_club(raw, side=slot)
        await message.answer(f"Беру «{club.name}» без клубных цветов. Если это клуб КХЛ, проверь написание.")
    await state.update_data(**{slot: club.to_dict()})
    await go_next(message, state, current, db, chrome_path)


@router.message(MatchSG.score, F.text, ~F.text.startswith("/"))
async def on_score(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    try:
        home_score, away_score = parse_score(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(home_score=home_score, away_score=away_score)
    await go_next(message, state, MatchSG.score, db, chrome_path)


@router.message(MatchSG.when, F.text, ~F.text.startswith("/"))
async def on_when(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    try:
        date, arena = parse_when(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(date=date, arena=arena)
    await go_next(message, state, MatchSG.when, db, chrome_path)


@router.message(MatchSG.periods, F.text, ~F.text.startswith("/"))
async def on_periods(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    try:
        periods = parse_periods(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(periods=periods)
    await go_next(message, state, MatchSG.periods, db, chrome_path)


@router.message(MatchSG.goals, F.text, ~F.text.startswith("/"))
async def on_goals(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    try:
        goals = parse_goals(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(goals=[asdict(goal) for goal in goals])
    await go_next(message, state, MatchSG.goals, db, chrome_path)


@router.message(MatchSG.footer, F.text, ~F.text.startswith("/"))
async def on_footer(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    try:
        footer = parse_footer(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(footer=footer.to_dict())
    await go_next(message, state, MatchSG.footer, db, chrome_path)


@router.message(MatchSG.note, F.text, ~F.text.startswith("/"))
async def on_note(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    note = (message.text or "").strip()
    if len(note) > 400:
        await message.answer("Сноска длиннее 400 знаков. Сократи её.")
        return
    await state.update_data(note=note)
    await go_next(message, state, MatchSG.note, db, chrome_path)


@router.message(MatchSG.photo, F.photo)
@router.message(MatchSG.photo, F.document)
async def on_photo(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    path = await _download_image(message, db)
    if path is None:
        await message.answer("Нужен кадр: фото или файл JPEG, PNG, WEBP.")
        return
    await state.update_data(photo_path=str(path))
    await go_next(message, state, MatchSG.photo, db, chrome_path)


@router.message(MatchSG.photo, F.text, ~F.text.startswith("/"))
async def photo_text(message: Message) -> None:
    await message.answer("Пришли фото или нажми «Пропустить».")


@router.callback_query(F.data == "post:publish")
async def publish(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    post = data.get("last_post")
    settings = db.settings(callback.from_user.id)
    if not post:
        await callback.answer("Сначала собери пост", show_alert=True)
        return
    if not settings.channel_id:
        await callback.answer("Сначала привяжи канал", show_alert=True)
        return
    caption, rest = split_caption(post["caption"])
    try:
        await callback.bot.send_photo(settings.channel_id, FSInputFile(post["path"]), caption=caption or None)
        if rest:
            await callback.bot.send_message(settings.channel_id, rest)
    except TelegramAPIError as exc:
        await callback.answer()
        await callback.message.answer(_publish_error(exc))
        return
    title = settings.channel_title or "канал"
    await callback.answer("Опубликовал")
    await callback.message.answer(f"Пост ушёл в {title}.")


@router.callback_query(F.data.startswith("post:texts:"))
async def choose_text(callback: CallbackQuery, db: Database) -> None:
    kind = callback.data.split(":", 2)[2]
    templates = [item for item in all_templates(db, callback.from_user.id) if item.kind == kind]
    await callback.answer()
    await callback.message.answer("Каким текстом подписать этот матч?", reply_markup=text_choice_kb(templates))


@router.callback_query(F.data.startswith("recap|"))
async def recap(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    template_id = callback.data.split("|", 1)[1]
    template = resolve_template(db, callback.from_user.id, template_id)
    data = await state.get_data()
    post = data.get("last_post")
    if not post:
        await callback.answer("Матч уже не на руках", show_alert=True)
        return
    if template.kind != post.get("kind"):
        await callback.answer("Этот шаблон другого типа", show_alert=True)
        return
    caption = render_caption(template.body, post["context"]) or post["caption"]
    post = {**post, "caption": caption, "template_id": template.id}
    await state.update_data(last_post=post)
    settings = db.settings(callback.from_user.id)
    caption_main, rest = split_caption(caption)
    await callback.answer("Текст обновлён")
    await callback.message.answer_photo(
        FSInputFile(post["path"]),
        caption=caption_main or None,
        reply_markup=None if rest else done_kb(has_channel=bool(settings.channel_id), kind=post["kind"]),
    )
    if rest:
        await callback.message.answer(
            rest,
            reply_markup=done_kb(has_channel=bool(settings.channel_id), kind=post["kind"]),
        )


@router.callback_query(F.data == "post:stay")
async def stay(callback: CallbackQuery) -> None:
    await callback.answer()


async def send_prompt(message: Message, state: FSMContext, step: State) -> None:
    data = await state.get_data()
    kind = data.get("kind", "result")
    steps = flow(kind)
    if step in steps:
        header = f"Шаг {steps.index(step) + 1} из {len(steps)} · {data.get('template_name', 'Матч')}"
    else:
        header = data.get("template_name", "Матч")
    text = f"{header}\n\n{_PROMPTS[step]}"
    await message.answer(text, reply_markup=wizard_kb(step, kind=kind))


async def go_next(
    message: Message,
    state: FSMContext,
    current: State,
    db: Database,
    chrome_path: str | None,
) -> None:
    data = await state.get_data()
    steps = flow(data.get("kind", "result"))
    if current not in steps:
        return
    index = steps.index(current)
    if index + 1 >= len(steps):
        await finish(message, state, db, chrome_path)
        return
    nxt = steps[index + 1]
    await state.set_state(nxt)
    await send_prompt(message, state, nxt)


async def import_from_khl(
    message: Message,
    state: FSMContext,
    db: Database,
    chrome_path: str | None,
) -> None:
    await message.answer("Смотрю протокол КХЛ и фото в каналах клубов…")
    try:
        imported = await asyncio.to_thread(load_match, message.text or "")
    except KhlError as exc:
        await message.answer(str(exc))
        return
    card = imported.card
    user_id = message.from_user.id if message.from_user else message.chat.id
    folder = db.path.parent / "uploads"
    target = folder / f"khl-{user_id}-{int(time.time())}.jpg"
    social_urls: list[str] = []
    if imported.played_at is not None:
        social_urls = await asyncio.to_thread(
            find_social_photos, card.home, card.away, imported.played_at
        )
    saved = None
    for photo_url in social_urls:
        saved = await asyncio.to_thread(download_match_photo, photo_url, target, False)
        if saved is not None:
            break
    if saved is None and imported.photo_url:
        saved = await asyncio.to_thread(download_match_photo, imported.photo_url, target, True)
    if saved is not None:
        card.photo_path = str(saved)
    settings = db.settings(user_id)
    template = resolve_template(db, user_id, settings.default_template)
    await state.update_data(
        template_id=template.id,
        template_name=template.name,
        kind="result",
        tournament=card.tournament,
        home=card.home.to_dict(),
        away=card.away.to_dict(),
        home_score=card.home_score,
        away_score=card.away_score,
        date=card.date,
        arena=card.arena,
        periods=list(card.periods),
        goals=[asdict(goal) for goal in card.goals],
        footer=card.footer.to_dict(),
        note=card.note,
        photo_path=card.photo_path,
        caption_override=imported.caption,
    )
    await finish(message, state, db, chrome_path)


async def finish(message: Message, state: FSMContext, db: Database, chrome_path: str | None) -> None:
    data = await state.get_data()
    if "home" not in data or "away" not in data:
        await message.answer("Не хватает команд. Начни матч заново.", reply_markup=menu_kb())
        return
    card = _card_from_state(data)
    user_id = message.chat.id
    template = resolve_template(db, user_id, data.get("template_id", "builtin:result"))
    caption = (data.get("caption_override") or "").strip()
    if caption:
        await state.update_data(caption_override="")
    else:
        caption = render_caption(template.body, build_context(card))
    if not caption:
        caption = f"{card.home.name} — {card.away.name}"
    renders = db.path.parent / "renders"
    dest = renders / f"{user_id}-{int(time.time())}.png"
    await message.answer("Собираю превью…")
    try:
        await asyncio.to_thread(render_poster, card, dest, chrome_path)
    except PosterError as exc:
        await message.answer(str(exc))
        return
    settings = db.settings(user_id)
    post = {
        "path": str(dest),
        "caption": caption,
        "kind": card.kind,
        "context": build_context(card),
        "template_id": template.id,
    }
    await state.set_state(None)
    await state.update_data(last_post=post)
    markup = done_kb(has_channel=bool(settings.channel_id), kind=card.kind)
    main_caption, rest = split_caption(caption)
    await message.answer_photo(
        FSInputFile(dest),
        caption=main_caption or None,
        reply_markup=None if rest else markup,
    )
    if rest:
        await message.answer(rest, reply_markup=markup)


async def _download_image(message: Message, db: Database) -> Path | None:
    if message.photo:
        source = message.photo[-1]
        suffix = ".jpg"
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        source = message.document
        suffix = {
            "image/png": ".png",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
        }.get(message.document.mime_type or "", ".jpg")
    else:
        return None
    folder = db.path.parent / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{message.chat.id}-{source.file_unique_id}{suffix}"
    telegram_file = await message.bot.get_file(source.file_id)
    await message.bot.download_file(telegram_file.file_path, dest)
    return dest


async def _clear_step(state: FSMContext, step: State) -> None:
    if step == MatchSG.when:
        await state.update_data(date="", arena="")
    elif step == MatchSG.periods:
        await state.update_data(periods=[])
    elif step == MatchSG.goals:
        await state.update_data(goals=[])
    elif step == MatchSG.footer:
        await state.update_data(footer=Footer().to_dict())
    elif step == MatchSG.note:
        await state.update_data(note="")
    elif step == MatchSG.photo:
        await state.update_data(photo_path=None)


async def _current(state: FSMContext) -> State | None:
    name = await state.get_state()
    for step in (*result_steps(), MatchSG.quick):
        if step.state == name:
            return step
    return None


def _card_from_state(data: dict) -> MatchCard:
    footer = data.get("footer")
    if not isinstance(footer, dict):
        footer = Footer().to_dict()
    return MatchCard(
        home=Club.from_dict(data["home"]),
        away=Club.from_dict(data["away"]),
        home_score=data.get("home_score"),
        away_score=data.get("away_score"),
        date=data.get("date") or "",
        arena=data.get("arena") or "",
        periods=list(data.get("periods") or []),
        goals=[Goal(**goal) for goal in data.get("goals") or []],
        footer=Footer.from_dict(footer),
        note=data.get("note") or "",
        photo_path=data.get("photo_path"),
        tournament=data.get("tournament") or "КХЛ · 26/27",
        kind=data.get("kind") or "result",
    )


def _require_known_or_custom(name: str, side: str):
    club, options = resolve_club(name, side=side)
    if options:
        names = ", ".join(item.name for item in options)
        raise ParseError(f"Неоднозначно «{name}»: {names}")
    return club


def _publish_error(exc: TelegramAPIError) -> str:
    text = str(exc).lower()
    if "not enough rights" in text or "forbidden" in text or "administrator" in text:
        return "Бот не может писать в канал. Сделай его администратором с правом публиковать."
    if "chat not found" in text:
        return "Канал не найден. Проверь /channel и что бот добавлен в канал."
    return "Не получилось опубликовать. Проверь права бота в канале."
