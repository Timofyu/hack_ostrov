from aiogram import F, Router
from aiogram.enums import ChatType

from hockeybot.handlers import common, day, match, result, table, templates


def setup_routers() -> Router:
    root = Router(name="root")
    root.message.filter(F.chat.type == ChatType.PRIVATE)
    root.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    root.include_router(common.router)
    root.include_router(templates.router)
    root.include_router(day.router)
    root.include_router(table.router)
    root.include_router(result.router)
    root.include_router(match.router)
    return root
