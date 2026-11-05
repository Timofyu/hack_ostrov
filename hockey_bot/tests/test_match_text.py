from pathlib import Path

from hockeybot.captions import build_context, render_caption, scorers_line
from hockeybot.db import Database
from hockeybot.models import Footer, Goal
from hockeybot.parsing import ParseError, parse_footer, parse_goals, parse_periods, parse_quick, parse_score
from hockeybot.teams import find_clubs
from hockeybot.templates_lib import demo_card


def test_score_and_periods() -> None:
    assert parse_score("5:0") == (5, 0)
    assert parse_score(" 3-2 ") == (3, 2)
    assert parse_periods("2:0, 1:0, 2:0") == ["2:0", "1:0", "2:0"]


def test_goals_with_tags() -> None:
    goals = parse_goals(
        "03:33 Родуолд — Кулик, Ремпал\n"
        "50:14 Ремпал (Родуолд) | мен\n"
        "55:43 Ремпал — Жаровский, Цулыгин | бол\n"
    )
    assert goals[0] == Goal("03:33", "Родуолд", "Кулик, Ремпал", "")
    assert goals[1].tag == "мен"
    assert goals[2].tag == "бол"
    assert scorers_line(goals) == "Родуолд, Ремпал ×2"


def test_footer_and_caption_drop_empty_lines() -> None:
    footer = parse_footer("Бочаров | 33 сейва | Шатаут\n33-й в карьере | | первый в сезоне")
    assert footer == Footer("Бочаров", "33 сейва", "Шатаут", "33-й в карьере", "", "первый в сезоне")
    card = demo_card()
    card.note = ""
    card.periods = []
    text = render_caption("{home}\n{periods_line}\n{note}\n{score}", build_context(card))
    assert text == "Салават Юлаев\n5:0"


def test_quick_block() -> None:
    parsed = parse_quick(
        "Салават Юлаев — Лада\n"
        "5:0\n"
        "4 ноября · Уфа-Арена\n"
        "2:0, 1:0, 2:0\n"
        "\n"
        "03:33 Родуолд — Кулик, Ремпал\n"
        "50:14 Ремпал — Родуолд | мен\n"
        "\n"
        "Бочаров | 33 сейва | Шатаут\n"
        "\n"
        "Серия из трёх поражений прервана\n"
        "6-е место Востока · 23 очка\n"
    )
    assert parsed["home_name"] == "Салават Юлаев"
    assert parsed["away_name"] == "Лада"
    assert parsed["home_score"] == 5
    assert parsed["date"] == "4 ноября"
    assert parsed["arena"] == "Уфа-Арена"
    assert parsed["periods"] == ["2:0", "1:0", "2:0"]
    assert len(parsed["goals"]) == 2
    assert parsed["footer"].left == "Бочаров"
    assert "6-е место" in parsed["note"]


def test_clubs_do_not_confuse_ska_and_cska() -> None:
    assert [club.name for club in find_clubs("ска")] == ["СКА"]
    assert [club.name for club in find_clubs("цска")] == ["ЦСКА"]
    assert {club.name for club in find_clubs("динамо")} == {"Динамо Москва", "Динамо Минск"}


def test_template_roundtrip(tmp_path: Path) -> None:
    db = Database(tmp_path / "bot.sqlite")
    saved = db.add_template(7, "Короткий вечер", "result", "{home} {score}")
    assert db.get_template(7, saved.id).body == "{home} {score}"
    db.set_default_template(7, saved.id)
    db.set_channel(7, "-1001", "Канал")
    settings = db.settings(7)
    assert settings.default_template == saved.id
    assert settings.channel_title == "Канал"
    assert db.delete_template(7, saved.id)


def test_bad_score() -> None:
    try:
        parse_score("пять ноль")
    except ParseError as exc:
        assert "5:0" in str(exc)
    else:
        raise AssertionError("expected ParseError")
