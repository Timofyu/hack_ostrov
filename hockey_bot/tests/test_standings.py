from datetime import datetime, timedelta, timezone

from hockeybot.db import Database
from hockeybot.khl import KhlError
from hockeybot.logos import logo_file
from hockeybot.standings import apply_movement, load_standings, snapshot_rows, standings_from_payload
from hockeybot.teams import normalize_name

TODAY = datetime(2026, 11, 7, 12, tzinfo=timezone(timedelta(hours=3)))


def _team(name: str, points: str, played: str = "10") -> dict:
    return {
        "name": name,
        "location": "Город",
        "gp": played,
        "w": "4",
        "otw": "1",
        "sow": "0",
        "sol": "1",
        "otl": "0",
        "l": "4",
        "pts": points,
        "gf": "30",
        "ga": "28",
    }


def _payload() -> list[dict]:
    west = [_team("ЦСКА", "20"), _team("Лада", "10")]
    east = [_team("Авангард", "18"), _team("Драконы", "12")]
    older = [_team("СКА", "90")]
    return [
        {"season": "2025/2026", "tables": {"west": older, "east": older}},
        {"season": "2026/2027", "tables": {"west": west, "east": east}},
    ]


def test_current_table_is_both_conferences() -> None:
    board = standings_from_payload(_payload(), "both", today=TODAY)
    assert board.tournament == "КХЛ · 26/27"
    assert board.as_of == "7 ноября"
    assert [item.title for item in board.conferences] == ["Запад", "Восток"]
    assert board.conferences[0].rows[0].name == "ЦСКА"
    assert board.conferences[0].rows[0].points == 20
    assert board.conferences[0].rows[0].playoff is True
    assert board.conferences[1].rows[1].name == "Драконы"
    assert "1. ЦСКА — 20 (10 игр, 30–28)" in board.caption
    assert "Первые 8 мест" not in board.caption


def test_one_conference_and_previous_season() -> None:
    board = standings_from_payload(_payload(), "east", today=TODAY)
    assert [item.key for item in board.conferences] == ["east"]
    previous = standings_from_payload(_payload(), "previous", today=TODAY)
    assert previous.tournament == "КХЛ · 25/26"
    assert previous.conferences[0].rows[0].name == "СКА"


def test_ninth_place_is_outside_the_playoff_line() -> None:
    west = [_team(f"ЦСКА {index}", str(30 - index)) for index in range(1, 10)]
    west[0]["name"] = "ЦСКА"
    payload = [{"season": "2026/2027", "tables": {"west": west, "east": [_team("Авангард", "1")]}}]
    board = standings_from_payload(payload, "west", today=TODAY)
    assert board.conferences[0].rows[7].playoff is True
    assert board.conferences[0].rows[8].playoff is False
    assert "Первые 8 мест" in board.caption


def test_movement_uses_the_previous_saved_day(tmp_path) -> None:
    board = standings_from_payload(_payload(), "both", today=TODAY)
    db = Database(tmp_path / "bot.sqlite")
    yesterday = []
    for conference, club, rank, points in snapshot_rows(board):
        if club == normalize_name("ЦСКА"):
            yesterday.append((conference, club, rank + 1, points - 2))
        else:
            yesterday.append((conference, club, rank, points))
    db.save_table_snapshot(board.season, "2026-11-06", yesterday)
    moved = apply_movement(board, db.previous_table(board.season, "2026-11-07"))
    cska = moved.conferences[0].rows[0]
    assert cska.move == 1
    assert cska.points_delta == 2
    assert "1. ЦСКА — 20 +2 ↑1" in moved.caption
    assert logo_file("Авангард") == "авангард.png"
    assert logo_file("Неизвестный клуб") == ""


def test_loader_uses_the_opener() -> None:
    def opener(url: str, params: dict) -> list:
        assert url.endswith("tables_v2.json")
        assert params["locale"] == "ru"
        return _payload()

    board = load_standings("both", opener=opener)
    assert board.conferences[0].rows[0].name == "ЦСКА"


def test_missing_previous_season() -> None:
    payload = [{"season": "2026/2027", "tables": {"west": [_team("ЦСКА", "1")], "east": []}}]
    try:
        standings_from_payload(payload, "previous", today=TODAY)
    except KhlError as exc:
        assert "Прошлого сезона" in str(exc)
    else:
        raise AssertionError("expected an error")
