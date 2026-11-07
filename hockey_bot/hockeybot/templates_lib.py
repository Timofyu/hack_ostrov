from __future__ import annotations

import re
from dataclasses import dataclass

from hockeybot.captions import build_context
from hockeybot.models import Club, Footer, Goal, MatchCard


@dataclass(frozen=True)
class PostTemplate:
    id: str
    name: str
    kind: str
    body: str
    builtin: bool = False


BUILTINS: tuple[PostTemplate, ...] = (
    PostTemplate(
        id="builtin:result",
        name="Итог матча",
        kind="result",
        builtin=True,
        body=(
            "{home} — {away}\n"
            "{score}\n"
            "\n"
            "{when}\n"
            "{periods_line}\n"
            "\n"
            "{goals_block}\n"
            "\n"
            "{note}\n"
            "\n"
            "{url}"
        ),
    ),
    PostTemplate(
        id="builtin:short",
        name="Коротко",
        kind="result",
        builtin=True,
        body="{home} {score} {away}\n{when}\n\n{scorers}",
    ),
    PostTemplate(
        id="builtin:shutout",
        name="Сухарь",
        kind="result",
        builtin=True,
        body=(
            "Сухой счёт\n"
            "{home} {score} {away}\n"
            "{when}\n"
            "\n"
            "{goalie_line}\n"
            "\n"
            "{goals_block}\n"
            "\n"
            "{note}"
        ),
    ),
    PostTemplate(
        id="builtin:announce",
        name="Анонс",
        kind="announce",
        builtin=True,
        body="Анонс\n{home} — {away}\n{when}\n\n{note}",
    ),
)

_BY_ID = {item.id: item for item in BUILTINS}

PLACEHOLDERS = (
    ("{home}", "хозяева"),
    ("{away}", "гости"),
    ("{home_city}", "город хозяев"),
    ("{away_city}", "город гостей"),
    ("{score}", "счёт, 5:0"),
    ("{home_score}", "шайбы хозяев"),
    ("{away_score}", "шайбы гостей"),
    ("{date}", "дата"),
    ("{arena}", "арена"),
    ("{when}", "дата и арена"),
    ("{periods_line}", "строка периодов"),
    ("{goals_block}", "список шайб"),
    ("{scorers}", "авторы через запятую"),
    ("{goalie_line}", "нижняя плашка одной строкой"),
    ("{note}", "сноска"),
    ("{tournament}", "турнир на превью"),
    ("{url}", "ссылка на протокол"),
)


def builtin(template_id: str) -> PostTemplate | None:
    return _BY_ID.get(template_id)


_RESULT_FIELD = re.compile(
    r"\{(home|away|score|home_score|away_score|goals_block|scorers|when|periods_line)\}"
)


def template_body_ok(body: str) -> str | None:
    text = body.strip()
    if len(text) < 8:
        return "Шаблон слишком короткий."
    if len(text) > 2000:
        return "Шаблон длиннее 2000 знаков."
    if _RESULT_FIELD.search(text) is None:
        return "В шаблоне нужно поле вроде {home}, {score} или {goals_block}."
    return None


def demo_card() -> MatchCard:
    return MatchCard(
        home=Club("Салават Юлаев", "Уфа", "#d6ff3c", "#d6ff3c", "#0a1408"),
        away=Club("Лада", "Тольятти", "#8eb6ee", "#1e4e96", "#f4f7ef"),
        home_score=5,
        away_score=0,
        date="4 ноября",
        arena="Уфа-Арена",
        periods=["2:0", "1:0", "2:0"],
        goals=[
            Goal("03:33", "Родуолд", "Кулик, Ремпал"),
            Goal("50:14", "Ремпал", "Родуолд", "мен"),
            Goal("55:43", "Ремпал", "Жаровский, Цулыгин", "бол"),
        ],
        footer=Footer("Бочаров", "33 сейва", "Шатаут", "33-й в карьере", "", "первый в сезоне"),
        note="Серия из трёх поражений прервана",
        tournament="КХЛ · 26/27",
        kind="result",
    )


def demo_context() -> dict[str, str]:
    return build_context(demo_card())
