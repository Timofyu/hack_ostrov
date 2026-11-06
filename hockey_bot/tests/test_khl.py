from datetime import date
from pathlib import Path

import pytest

from hockeybot.khl import (
    KhlError,
    club_key,
    load_match,
    match_from_event,
    match_photo_url,
    parse_request,
    period_lines,
)


TODAY = date(2026, 11, 6)

EVENT = {
    "id": 3001047,
    "khl_id": 902224,
    "outer_stage_id": 1436,
    "game_state_key": "finished",
    "score": "2:1",
    "season": "2026/2027",
    "event_start_at": 1793884800000,
    "start_at": 1793885400000,
    "scores": {
        "first_period": "0:0",
        "second_period": "0:0",
        "third_period": "1:1",
        "overtime": "1:0",
        "bullitt": None,
    },
    "arena": {"name": "«G-Drive Арена»"},
    "team_a": {
        "id": 10,
        "name": "Авангард",
        "location": "Омск",
        "shots": 24,
        "players": [
            {"name": "Просветов Иван", "role_key": "goaltender", "match_stats": [{"id": "toi", "val": 0}]},
            {"name": "Серебряков Никита", "role_key": "goaltender", "match_stats": [{"id": "toi", "val": 60.4}]},
        ],
    },
    "team_b": {
        "id": 16,
        "name": "ЦСКА",
        "location": "Москва",
        "shots": 26,
        "players": [
            {"name": "Гамзин Дмитрий", "role_key": "goaltender", "match_stats": [{"id": "toi", "val": 60.4}]},
        ],
    },
    "goals": [
        {
            "time": 3624,
            "period": 4,
            "status": "В равенстве",
            "status_abbr": "рав",
            "author": {"name": "Окулов Константин", "team_id": 10},
            "assistants": [{"name": "Гуляев Михаил"}, {"name": "Маклауд Майкл"}],
        },
        {
            "time": 3306,
            "period": 3,
            "status": "В большинстве",
            "status_abbr": "бол",
            "author": {"name": "Полтапов Прохор", "team_id": 16},
            "assistants": [{"name": "Хайруллин Марат"}],
        },
    ],
    "violations": [
        {
            "time": 2711,
            "penalty_time": 2,
            "penalty_reason": "Подножка",
            "violator": {"name": "Дроздов Иван", "team_id": 16},
        }
    ],
}


def test_parse_teams_and_date() -> None:
    request = parse_request("Авангард ЦСКА 5 ноября 2026", today=TODAY)
    assert (request.left, request.right, request.day) == ("Авангард", "ЦСКА", date(2026, 11, 5))
    dashed = parse_request("ЦСКА — Авангард 05.11.2026", today=TODAY)
    assert (dashed.left, dashed.right) == ("ЦСКА", "Авангард")
    long_names = parse_request("Салават Юлаев Лада 4 ноября", today=TODAY)
    assert long_names.left == "Салават Юлаев"
    assert long_names.right == "Лада"
    assert long_names.day == date(2026, 11, 4)
    january = parse_request("Динамо Москва СКА 1 января", today=TODAY)
    assert january.day == date(2027, 1, 1)
    with pytest.raises(KhlError):
        parse_request("Авангард ЦСКА", today=TODAY)


def test_api_names_match_palette() -> None:
    assert club_key("Динамо М") == club_key("Динамо Москва")
    assert club_key("Динамо Мн") == club_key("Динамо Минск")
    assert club_key("Металлург Мг") == club_key("Металлург")
    assert club_key("ХК Сочи") == club_key("Сочи")


def test_overtime_periods_are_not_cumulative() -> None:
    assert period_lines(EVENT["scores"], [], 10) == ["0:0", "0:0", "1:1", "1:0"]
    cumulative = {
        "first_period": "1:0",
        "second_period": "1:1",
        "third_period": "1:1",
        "overtime": "2:1",
    }
    assert period_lines(cumulative, [], 10) == ["1:0", "0:1", "0:0", "1:0"]


def test_event_becomes_protocol_and_card() -> None:
    imported = match_from_event(EVENT)
    card = imported.card
    assert card.home.name == "Авангард"
    assert card.away.name == "ЦСКА"
    assert (card.home_score, card.away_score) == (2, 1)
    assert card.date == "5 ноября"
    assert card.arena == "G-Drive Арена"
    assert card.periods == ["0:0", "0:0", "1:1", "1:0"]
    assert card.tournament == "КХЛ · 26/27"
    assert [(goal.time, goal.scorer, goal.tag) for goal in card.goals] == [
        ("55:06", "Полтапов", "бол"),
        ("60:24", "Окулов", ""),
    ]
    assert card.goals[1].assists == "Гуляев, Маклауд"
    assert card.footer.left == "Серебряков"
    assert card.footer.center == "25 сейвов"
    assert card.footer.right == "Овертайм"
    assert "Победа в овертайме" == card.note
    assert "55:06 Полтапов (Хайруллин), бол." in imported.caption
    assert "60:24 Окулов (Гуляев, Маклауд)" in imported.caption
    assert "Броски в створ: 24–26" in imported.caption
    assert "Серебряков (Авангард) — 25 сейвов" in imported.caption
    assert "Гамзин (ЦСКА) — 22 сейва" in imported.caption
    assert "45:11 Дроздов (ЦСКА), 2 мин, подножка" in imported.caption
    assert imported.caption.endswith("https://www.khl.ru/game/1436/902224/resume/")


def test_photo_url_prefers_the_latest_goal_frame() -> None:
    event = {
        "image_big": "https://cdn.example/wide.jpg",
        "goals": [
            {"time": 100, "quote": {"image_url": "https://cdn.example/first.jpg"}},
            {"time": 400, "quote": {"image_url": "https://cdn.example/winner.jpg"}},
        ],
    }
    assert match_photo_url(event) == "https://cdn.example/winner.jpg"
    assert match_photo_url({"image_big": "https://cdn.example/wide.jpg", "goals": []}) == "https://cdn.example/wide.jpg"
    assert match_photo_url({}) == ""


def test_broadcast_bar_is_cropped(tmp_path: Path) -> None:
    from PIL import Image

    from hockeybot.photos import _without_broadcast_bar, download_match_photo

    frame = Image.new("RGB", (1280, 720), (20, 40, 30))
    cropped = _without_broadcast_bar(frame)
    assert cropped.size == (1280, int(720 * 0.84))
    square = Image.new("RGB", (800, 800), (1, 1, 1))
    assert _without_broadcast_bar(square).size == (800, 800)
    assert download_match_photo("http://example.com/a.jpg", tmp_path / "nope.jpg") is None


def test_social_gallery_beats_a_later_promo() -> None:
    from datetime import datetime, timezone

    from hockeybot.models import Club
    from hockeybot.social import ChannelPost, choose_post, parse_telegram_channel

    played = datetime(2026, 11, 5, 13, 30, tzinfo=timezone.utc)
    cska = Club("ЦСКА", "Москва", "#fff", "#fff", "#000", ("цска",))
    victory = ChannelPost(
        10,
        datetime(2026, 11, 5, 18, 23, tzinfo=timezone.utc),
        "Победа! Альбом с матча против ЦСКА",
        ("https://cdn4.telesco.pe/file/a.jpg",) * 6,
    )
    promo = ChannelPost(
        11,
        datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc),
        "Ждём Сибирь, билеты уже в продаже",
        ("https://cdn4.telesco.pe/file/b.jpg",) * 8,
    )
    graphic = ChannelPost(
        12,
        datetime(2026, 11, 5, 19, 0, tzinfo=timezone.utc),
        "Лучший игрок матча против ЦСКА",
        ("https://cdn4.telesco.pe/file/one.jpg",),
    )
    assert choose_post([promo, graphic, victory], cska, played) == victory

    html = """
    <div class="tgme_widget_message " data-post="omskiyavangard/10">
      <div class="tgme_widget_message_text">Победа над ЦСКА</div>
      <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn4.telesco.pe/file/win.jpg')"></a>
      <time datetime="2026-11-05T18:23:51+00:00"></time>
    </div>
    """
    parsed = parse_telegram_channel(html)
    assert parsed[0].photos == ("https://cdn4.telesco.pe/file/win.jpg",)
    assert parsed[0].post_id == 10


def test_load_match_uses_calendar_then_protocol() -> None:
    calls: list[str] = []

    def opener(url: str, params: dict) -> dict | list:
        calls.append(url)
        if url.endswith("events_v2.json"):
            return [{"event": {"id": 3001047, "type_id": 24, "game_state_key": "finished", "team_a": {"name": "ЦСКА"}, "team_b": {"name": "Авангард"}, "score": "1:2", "start_at": 1}}]
        return {"event": EVENT}

    imported = load_match("ЦСКА Авангард 5 ноября 2026", today=TODAY, opener=opener)
    assert calls[0].endswith("events_v2.json")
    assert "id" in calls[1] or calls[1].endswith("event_v2.json")
    assert imported.card.home.name == "Авангард"
    assert imported.card.home_score == 2


def test_missing_game_lists_the_day() -> None:
    def opener(url: str, params: dict) -> dict | list:
        if url.endswith("events_v2.json"):
            return [{"event": {"id": 1, "type_id": 24, "team_a": {"name": "Лада"}, "team_b": {"name": "Сочи"}, "score": "3:2", "game_state_key": "finished"}}]
        raise AssertionError("protocol should not be requested")

    with pytest.raises(KhlError) as exc:
        load_match("Авангард ЦСКА 5 ноября 2026", today=TODAY, opener=opener)
    assert "Лада — Сочи 3:2" in str(exc.value)
