from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from hockeybot.khl import KhlError, MSK, _russian_date, club_from_api, games_on

_PLAYED = {"finished", "in_progress"}


@dataclass(frozen=True)
class DayGame:
    time: str
    home: str
    away: str
    home_city: str
    away_city: str
    home_mark: str
    away_mark: str
    place: str
    score: str
    live: bool


@dataclass(frozen=True)
class DaySlate:
    tournament: str
    date_label: str
    year: int
    games: tuple[DayGame, ...]
    caption: str


def load_day(day: date, *, opener=None) -> DaySlate:
    events = games_on(day, opener=opener)
    if not events:
        raise KhlError(f"На {_russian_date(day)} {day.year} в календаре КХЛ нет матчей.")
    games = tuple(_game(event) for event in events)
    stage = str(events[0].get("stage_name") or "")
    tournament = _tournament(stage)
    label = _russian_date(day)
    return DaySlate(
        tournament=tournament,
        date_label=label,
        year=day.year,
        games=games,
        caption=_caption(tournament, label, day.year, games),
    )


def _game(event: dict) -> DayGame:
    home_raw = event.get("team_a") or {}
    away_raw = event.get("team_b") or {}
    home = club_from_api(home_raw, side="home")
    away = club_from_api(away_raw, side="away")
    state = str(event.get("game_state_key") or "")
    score = str(event.get("score") or "").strip() if state in _PLAYED else ""
    place = str(home_raw.get("location") or event.get("location") or home.city or "").strip()
    return DayGame(
        time=_clock(event.get("start_at") or event.get("event_start_at")),
        home=home.name,
        away=away.name,
        home_city=home.city or str(home_raw.get("location") or ""),
        away_city=away.city or str(away_raw.get("location") or ""),
        home_mark=home.mark,
        away_mark=away.mark,
        place=place,
        score=score if ":" in score else "",
        live=state == "in_progress",
    )


def _caption(tournament: str, label: str, year: int, games: tuple[DayGame, ...]) -> str:
    lines = ["Превью дня", f"{label} {year}", tournament, ""]
    for game in games:
        middle = f" {game.score}" if game.score else ""
        tail = f", {game.place}" if game.place else ""
        live = " · идёт" if game.live else ""
        lines.append(f"{game.time} {game.home} — {game.away}{middle}{tail}{live}".strip())
    return "\n".join(lines).strip()


def _tournament(stage_name: str) -> str:
    match = re.search(r"(\d{4})\s*/\s*(\d{4})", stage_name or "")
    if not match:
        return "КХЛ"
    return f"КХЛ · {match.group(1)[2:]}/{match.group(2)[2:]}"


def _clock(stamp: object) -> str:
    if not isinstance(stamp, (int, float)) or stamp <= 0:
        return ""
    seconds = stamp / 1000 if stamp > 10**12 else stamp
    return datetime.fromtimestamp(seconds, tz=MSK).strftime("%H:%M")
