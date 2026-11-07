from datetime import date, datetime, timedelta, timezone

import pytest

from hockeybot.daypreview import load_day
from hockeybot.khl import KhlError, games_on, parse_calendar_day

TODAY = date(2026, 11, 7)
MSK = timezone(timedelta(hours=3))


def test_calendar_day_words_and_numbers() -> None:
    assert parse_calendar_day("сегодня", today=TODAY) == TODAY
    assert parse_calendar_day("завтра", today=TODAY) == date(2026, 11, 8)
    assert parse_calendar_day("8 ноября", today=TODAY) == date(2026, 11, 8)
    assert parse_calendar_day("08.11.2025", today=TODAY) == date(2025, 11, 8)
    with pytest.raises(KhlError):
        parse_calendar_day("Авангард ЦСКА 8 ноября", today=TODAY)


def test_day_slate_hides_a_score_that_has_not_started() -> None:
    start = int(datetime(2026, 11, 8, 14, 0, tzinfo=MSK).timestamp() * 1000)

    def opener(url: str, params: dict) -> list:
        assert url.endswith("events_v2.json")
        return [
            {
                "event": {
                    "type_id": 24,
                    "start_at": start,
                    "game_state_key": "not_yet_started",
                    "score": "0:0",
                    "stage_name": "Регулярный чемпионат 2026/2027",
                    "location": "Омск",
                    "team_a": {"name": "Авангард", "location": "Омск"},
                    "team_b": {"name": "Сибирь", "location": "Новосибирск"},
                }
            }
        ]

    slate = load_day(date(2026, 11, 8), opener=opener)
    assert slate.tournament == "КХЛ · 26/27"
    assert slate.date_label == "8 ноября"
    game = slate.games[0]
    assert game.time == "14:00"
    assert (game.home, game.away, game.score) == ("Авангард", "Сибирь", "")
    assert "14:00 Авангард — Сибирь, Омск" in slate.caption


def test_finished_day_keeps_the_score() -> None:
    def opener(url: str, params: dict) -> list:
        return [
            {
                "event": {
                    "type_id": 18,
                    "start_at": 1_778_000_000_000,
                    "game_state_key": "finished",
                    "score": "2:1",
                    "stage_name": "Регулярный чемпионат 2026/2027",
                    "team_a": {"name": "ЦСКА", "location": "Москва"},
                    "team_b": {"name": "СКА", "location": "Санкт-Петербург"},
                }
            }
        ]

    slate = load_day(date(2026, 11, 5), opener=opener)
    assert slate.games[0].score == "2:1"
    assert "2:1" in slate.caption


def test_empty_day_is_an_error() -> None:
    def opener(url: str, params: dict):
        if url.endswith("data.json"):
            return {"stages_v2": []}
        return []

    assert games_on(date(2026, 5, 21), opener=opener) == []
    with pytest.raises(KhlError, match="нет матчей"):
        load_day(date(2026, 5, 21), opener=opener)
