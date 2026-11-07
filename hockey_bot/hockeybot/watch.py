from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import FSInputFile

from hockeybot.captions import split_caption
from hockeybot.db import Database, Watch
from hockeybot.delivery import compose_result
from hockeybot.keyboards import done_kb, waiting_kb
from hockeybot.khl import KhlError, load_match
from hockeybot.poster import PosterError

log = logging.getLogger(__name__)

POLL_SECONDS = 120
MAX_AGE = timedelta(hours=36)


def watch_action(error: str | None, finished: bool | None) -> str:
    """ready — протокол закрыт, wait — ещё рано или сайт молчит, drop — запрос не про матч."""
    if error is None and finished:
        return "ready"
    if error is None and finished is False:
        return "wait"
    text = error or ""
    if text.startswith("Матч ещё не начался") or "не отвечает" in text or "неожиданном виде" in text:
        return "wait"
    return "drop"


def wait_notice(error: str | None) -> str:
    text = error or ""
    if text.startswith("Матч ещё не начался"):
        return (
            f"{text}\n\n"
            "Как только КХЛ закроет протокол, соберу пост по твоему шаблону и пришлю сюда."
        )
    if "не отвечает" in text or "неожиданном виде" in text:
        return (
            "Сайт КХЛ сейчас не отвечает. Слежу дальше и пришлю пост, "
            "когда протокол появится. Если ждать не хочется — собери вручную."
        )
    return (
        "Матч ещё идёт. Как только КХЛ закроет протокол, "
        "соберу пост по твоему шаблону и пришлю сюда."
    )


def _age(created_at: str) -> timedelta:
    stamp = datetime.fromisoformat(created_at)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - stamp


async def watch_loop(bot: Bot, db: Database, chrome_path: str | None, storage: BaseStorage) -> None:
    await asyncio.sleep(15)
    me = await bot.me()
    while True:
        try:
            await sweep(bot, db, chrome_path, storage, me.id)
        except Exception:
            log.exception("watch sweep failed")
        await asyncio.sleep(POLL_SECONDS)


async def sweep(
    bot: Bot,
    db: Database,
    chrome_path: str | None,
    storage: BaseStorage,
    bot_id: int,
) -> None:
    for watch in db.pending_watches():
        try:
            await _one(bot, db, chrome_path, storage, bot_id, watch)
        except Exception:
            log.exception("watch %s failed", watch.id)


async def _one(
    bot: Bot,
    db: Database,
    chrome_path: str | None,
    storage: BaseStorage,
    bot_id: int,
    watch: Watch,
) -> None:
    if _age(watch.created_at) > MAX_AGE:
        db.finish_watch(watch.id, "expired")
        await _tell(
            bot,
            watch.chat_id,
            f"Протокол так и не появился. Слежку за «{watch.query}» остановил.",
            reply_markup=waiting_kb(),
        )
        return
    try:
        imported = await asyncio.to_thread(load_match, watch.query)
    except KhlError as exc:
        action = watch_action(str(exc), None)
        if action == "wait":
            return
        db.finish_watch(watch.id, "failed")
        await _tell(bot, watch.chat_id, str(exc), reply_markup=waiting_kb())
        return
    if watch_action(None, imported.finished) != "ready":
        return
    try:
        post = await compose_result(imported, watch.owner_id, db, chrome_path)
    except PosterError:
        log.exception("poster failed for watch %s", watch.id)
        return
    try:
        await _deliver(bot, db, storage, bot_id, watch, post)
    except TelegramAPIError:
        log.exception("telegram failed for watch %s", watch.id)
        return
    db.finish_watch(watch.id, "done")


async def _deliver(bot: Bot, db: Database, storage: BaseStorage, bot_id: int, watch: Watch, post: dict) -> None:
    key = StorageKey(bot_id=bot_id, chat_id=watch.chat_id, user_id=watch.owner_id)
    current = await storage.get_data(key)
    current["last_post"] = post
    await storage.set_data(key, current)
    settings = db.settings(watch.owner_id)
    markup = done_kb(has_channel=bool(settings.channel_id), kind="result")
    caption, rest = split_caption(post["caption"])
    await bot.send_message(watch.chat_id, "Матч закончился. Вот пост по твоему шаблону.")
    await bot.send_photo(
        watch.chat_id,
        FSInputFile(post["path"]),
        caption=caption or None,
        reply_markup=None if rest else markup,
    )
    if rest:
        await bot.send_message(watch.chat_id, rest, reply_markup=markup)


async def _tell(bot: Bot, chat_id: int, text: str, reply_markup) -> None:
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        log.exception("could not notify chat %s", chat_id)
