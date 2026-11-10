from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from hockeybot.db import Database
from hockeybot.keyboards import channel_kb, menu_kb
from hockeybot.templates_lib import PLACEHOLDERS

router = Router(name="common")

HELP = (
    "Собираю превью матча и текст поста для канала.\n\n"
    "Напиши встречу и дату одной строкой:\n"
    "Авангард ЦСКА 5 ноября 2026\n"
    "Локомотив Ак Барс 21 мая 2026\n\n"
    "Под фото матча короткий текст: счёт, дата и авторы шайб. "
    "Картинка в одном оформлении, на ней протокол и логотипы клубов. "
    "Данные с khl.ru, кадр — из телеграм-канала клуба. "
    "Если матч ещё идёт, пост придёт сам, когда протокол закроется.\n\n"
    "Бот отвечает в Telegram с телефона и с компьютера. "
    "Чтобы он не замолкал при выключенном домашнем ПК, его держат на сервере.\n\n"
    "Создать пост — итоги матча, итоги дня, таблица или превью дня.\n"
    "Таблица показывает очки и как изменилось место со вчерашнего сохранённого дня.\n"
    "Шаблоны — свои тексты для других постов.\n"
    "Канал — куда публиковать готовый пост. Бот должен быть администратором.\n\n"
    "Команды: /match, /templates, /channel, /cancel"
)


def placeholder_help() -> str:
    lines = ["Поля шаблона:"]
    for key, title in PLACEHOLDERS:
        lines.append(f"{key} — {title}")
    lines.append("\nПустое поле убирает строку, в которой оно одно.")
    return "\n".join(lines)


@router.message(CommandStart())
@router.message(Command("help"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP, reply_markup=menu_kb())


@router.message(Command("cancel"))
@router.callback_query(F.data == "wiz:cancel")
async def cancel(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = "Остановил. Черновик стёрт."
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=menu_kb())
        return
    await event.answer(text, reply_markup=menu_kb())


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await callback.answer()
    await callback.message.answer(HELP, reply_markup=menu_kb())


@router.message(Command("channel"))
@router.callback_query(F.data == "menu:channel")
async def channel_help(event: Message | CallbackQuery, db: Database) -> None:
    message = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    user_id = event.from_user.id
    settings = db.settings(user_id)
    if isinstance(event, Message) and event.text and event.text.startswith("/channel "):
        argument = event.text.split(maxsplit=1)[1].strip()
        if argument.lower() in {"off", "clear", "сброс"}:
            db.clear_channel(user_id)
            await message.answer("Канал отвязан.", reply_markup=menu_kb())
            return
        await _link_channel(message, db, user_id, argument)
        return
    if settings.channel_id:
        title = settings.channel_title or settings.channel_id
        await message.answer(
            f"Сейчас публикую в {title}.\n\n"
            "Чтобы сменить, пришли /channel @имя_канала.\n"
            "Бот должен быть администратором с правом публиковать сообщения.",
            reply_markup=channel_kb(True),
        )
        return
    await message.answer(
        "Канал ещё не привязан.\n\n"
        "Добавь бота в канал администратором и пришли /channel @имя_канала",
        reply_markup=channel_kb(False),
    )


@router.callback_query(F.data == "channel:clear")
async def channel_clear(callback: CallbackQuery, db: Database) -> None:
    db.clear_channel(callback.from_user.id)
    await callback.answer("Канал отвязан")
    await callback.message.answer("Канал отвязан.", reply_markup=menu_kb())


async def _link_channel(message: Message, db: Database, user_id: int, argument: str) -> None:
    try:
        chat = await message.bot.get_chat(argument)
    except Exception:
        await message.answer(
            "Не вижу такой канал. Проверь @имя и что бот уже добавлен в него."
        )
        return
    if chat.type not in {"channel", "supergroup", "group"}:
        await message.answer("Нужен канал или группа, не личный чат.")
        return
    title = chat.title or argument
    db.set_channel(user_id, str(chat.id), title)
    await message.answer(f"Буду публиковать в {title}.", reply_markup=menu_kb())
