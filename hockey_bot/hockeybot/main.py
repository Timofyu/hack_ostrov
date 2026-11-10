from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, TelegramObject

from hockeybot.config import Config, load_config
from hockeybot.db import Database
from hockeybot.handlers import setup_routers
from hockeybot.watch import watch_loop


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed: frozenset[int]):
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.allowed:
            return await handler(event, data)
        user = data.get("event_from_user")
        if user is not None and user.id in self.allowed:
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer("Этот бот закрытый.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Нет доступа", show_alert=True)
        return None


async def run(config: Config) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bot = Bot(config.token)
    database = Database(config.db_path)
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        db=database,
        chrome_path=config.chrome_path,
    )
    dispatcher.message.middleware(AccessMiddleware(config.allowed_user_ids))
    dispatcher.callback_query.middleware(AccessMiddleware(config.allowed_user_ids))
    dispatcher.include_router(setup_routers())

    async def _start_watch(bot: Bot) -> None:
        asyncio.create_task(watch_loop(bot, database, config.chrome_path, dispatcher.storage))

    dispatcher.startup.register(_start_watch)
    await dispatcher.start_polling(bot)


def main() -> None:
    asyncio.run(run(load_config()))
