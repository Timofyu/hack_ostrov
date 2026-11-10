from __future__ import annotations

from aiogram.fsm.state import State
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from hockeybot.models import Club
from hockeybot.states import MatchSG
from hockeybot.templates_lib import PostTemplate


def dock_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Итоги матча"), KeyboardButton(text="Итоги дня")],
            [KeyboardButton(text="Таблица"), KeyboardButton(text="Превью дня")],
            [KeyboardButton(text="Шаблоны"), KeyboardButton(text="Канал")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Клубы и дата или кнопка внизу",
    )


def menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Создать пост", callback_data="menu:create")
    builder.button(text="Шаблоны", callback_data="menu:templates")
    builder.button(text="Канал", callback_data="menu:channel")
    builder.adjust(1)
    return builder.as_markup()


def create_post_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Итоги матча", callback_data="menu:match")
    builder.button(text="Итоги дня", callback_data="menu:results")
    builder.button(text="Таблица", callback_data="menu:table")
    builder.button(text="Превью дня", callback_data="menu:day")
    builder.button(text="В меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def day_done_kb(*, has_channel: bool, results: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_channel:
        builder.button(text="Опубликовать в канал", callback_data="post:publish")
    builder.button(text="Другой день", callback_data="menu:results" if results else "menu:day")
    builder.button(text="Создать пост", callback_data="menu:create")
    builder.adjust(1)
    return builder.as_markup()


def day_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сегодня", callback_data="day:today")
    builder.button(text="Завтра", callback_data="day:tomorrow")
    builder.button(text="Назад", callback_data="menu:create")
    builder.adjust(2, 1)
    return builder.as_markup()


def table_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Запад и Восток", callback_data="table:both")
    builder.button(text="Только Запад", callback_data="table:west")
    builder.button(text="Только Восток", callback_data="table:east")
    builder.button(text="Прошлый сезон", callback_data="table:previous")
    builder.button(text="В меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def table_done_kb(*, has_channel: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_channel:
        builder.button(text="Опубликовать в канал", callback_data="post:publish")
    builder.button(text="Другая таблица", callback_data="menu:table")
    builder.button(text="Создать пост", callback_data="menu:create")
    builder.adjust(1)
    return builder.as_markup()


def wizard_kb(step: State, *, kind: str) -> InlineKeyboardMarkup:
    steps = announce_steps() if kind == "announce" else result_steps()
    builder = InlineKeyboardBuilder()
    if step == steps[0]:
        builder.button(text="Отмена", callback_data="wiz:cancel")
        builder.button(text="Одним сообщением", callback_data="wiz:quick")
    else:
        builder.button(text="Назад", callback_data="wiz:back")
    if step not in {MatchSG.home, MatchSG.away, MatchSG.score, MatchSG.quick}:
        builder.button(text="Пропустить", callback_data="wiz:skip")
    builder.adjust(2)
    return builder.as_markup()


def clubs_kb(clubs: list[Club]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, club in enumerate(clubs):
        builder.button(text=club.name, callback_data=f"club:{index}")
    builder.adjust(1)
    return builder.as_markup()


def done_kb(*, has_channel: bool, kind: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_channel:
        builder.button(text="Опубликовать в канал", callback_data="post:publish")
    if kind == "result":
        builder.button(text="Поменять картинку", callback_data="post:photo")
        builder.button(text="Собрать вручную", callback_data="menu:manual")
    builder.button(text="Другой текст", callback_data=f"post:texts:{kind}")
    builder.button(text="Создать пост", callback_data="menu:create")
    builder.adjust(1)
    return builder.as_markup()


def result_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Прислать шаблон", callback_data="result:template")
    builder.button(text="Собрать по протоколу", callback_data="result:query")
    builder.button(text="Собрать вручную", callback_data="menu:manual")
    builder.button(text="Назад", callback_data="menu:create")
    builder.adjust(1)
    return builder.as_markup()


def waiting_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Собрать вручную", callback_data="menu:manual")
    builder.button(text="Не следить", callback_data="watch:stop")
    builder.adjust(1)
    return builder.as_markup()


def template_list_kb(templates: list[PostTemplate], default_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for template in templates:
        mark = " · основной" if template.id == default_id else ""
        builder.button(text=f"{template.name}{mark}", callback_data=f"topen|{template.id}")
    builder.button(text="Новый шаблон", callback_data="tnew")
    builder.button(text="Надпись турнира", callback_data="ttournament")
    builder.button(text="В меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def template_card_kb(template: PostTemplate) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сделать основным", callback_data=f"tdef|{template.id}")
    if template.builtin:
        builder.button(text="Скопировать", callback_data=f"tcopy|{template.id}")
    else:
        builder.button(text="Изменить текст", callback_data=f"tedit|{template.id}")
        builder.button(text="Удалить", callback_data=f"tdel|{template.id}")
    builder.button(text="К списку", callback_data="menu:templates")
    builder.adjust(1)
    return builder.as_markup()


def kind_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Итог матча", callback_data="tkind|result")
    builder.button(text="Анонс", callback_data="tkind|announce")
    builder.adjust(1)
    return builder.as_markup()


def keep_text_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Оставить текст", callback_data="tkeep")
    builder.button(text="Отмена", callback_data="wiz:cancel")
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_kb(template_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить", callback_data=f"tdelyes|{template_id}")
    builder.button(text="Оставить", callback_data=f"topen|{template_id}")
    builder.adjust(2)
    return builder.as_markup()


def text_choice_kb(templates: list[PostTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for template in templates:
        builder.button(text=template.name, callback_data=f"recap|{template.id}")
    builder.button(text="Назад к посту", callback_data="post:stay")
    builder.adjust(1)
    return builder.as_markup()


def channel_kb(linked: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if linked:
        builder.button(text="Отвязать канал", callback_data="channel:clear")
    builder.button(text="В меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def result_steps() -> list[State]:
    return [
        MatchSG.home,
        MatchSG.away,
        MatchSG.score,
        MatchSG.when,
        MatchSG.periods,
        MatchSG.goals,
        MatchSG.footer,
        MatchSG.note,
        MatchSG.photo,
    ]


def announce_steps() -> list[State]:
    return [MatchSG.home, MatchSG.away, MatchSG.when, MatchSG.note, MatchSG.photo]
