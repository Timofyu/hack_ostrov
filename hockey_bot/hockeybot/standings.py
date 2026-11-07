from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from hockeybot.khl import KhlError, _open_json, club_from_api

MSK = timezone(timedelta(hours=3))
TABLES_URLS = (
    "https://api-video.khl.ru/api/khl_mobile/tables_v2.json",
    "https://khl.api.webcaster.pro/api/khl_mobile/tables_v2.json",
)
_SCOPES = {"both", "west", "east", "previous"}
_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_PLAYOFF_PLACES = 8


@dataclass(frozen=True)
class TableRow:
    rank: int
    name: str
    city: str
    mark: str
    played: int
    points: int
    goals_for: int
    goals_against: int
    wins: int
    ot_wins: int
    so_wins: int
    so_losses: int
    ot_losses: int
    losses: int
    playoff: bool


@dataclass(frozen=True)
class Conference:
    key: str
    title: str
    rows: tuple[TableRow, ...]


@dataclass(frozen=True)
class Standings:
    tournament: str
    season: str
    stage: str
    as_of: str
    conferences: tuple[Conference, ...]
    caption: str


def load_standings(scope: str, *, opener=None) -> Standings:
    if scope not in _SCOPES:
        raise KhlError("Такой таблицы нет.")
    fetch = opener or _open_json
    payload = _fetch_tables(fetch)
    return standings_from_payload(payload, scope)


def standings_from_payload(payload: object, scope: str, *, today: datetime | None = None) -> Standings:
    seasons = _seasons(payload)
    if not seasons:
        raise KhlError("КХЛ не отдала турнирную таблицу. Попробуй ещё раз через минуту.")
    seasons.sort(key=lambda item: _season_key(item[0]), reverse=True)
    if scope == "previous":
        if len(seasons) < 2:
            raise KhlError("Прошлого сезона в таблице КХЛ нет.")
        season, tables = seasons[1]
    else:
        season, tables = seasons[0]
    wanted = ("west", "east") if scope in {"both", "previous"} else (scope,)
    conferences = tuple(
        _conference(key, tables.get(key) or [])
        for key in wanted
        if tables.get(key)
    )
    if not conferences:
        raise KhlError("В этой таблице пока нет клубов.")
    moment = today or datetime.now(MSK)
    as_of = f"{moment.day} {_MONTHS[moment.month - 1]}"
    tournament = _tournament(season)
    stage = "Регулярный чемпионат"
    return Standings(
        tournament=tournament,
        season=season,
        stage=stage,
        as_of=as_of,
        conferences=conferences,
        caption=_caption(tournament, stage, as_of, conferences),
    )


def _fetch_tables(fetch) -> object:
    last: Exception | None = None
    for url in TABLES_URLS:
        try:
            return fetch(url, {"locale": "ru"})
        except Exception as exc:
            last = exc
    raise KhlError("Сайт КХЛ сейчас не отвечает. Попробуй ещё раз через минуту.") from last


def _seasons(payload: object) -> list[tuple[str, dict]]:
    if not isinstance(payload, list):
        return []
    found: list[tuple[str, dict]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        season = str(row.get("season") or "").strip()
        tables = row.get("tables")
        if not season or not isinstance(tables, dict):
            continue
        if not tables.get("west") and not tables.get("east"):
            continue
        found.append((season, tables))
    return found


def _conference(key: str, rows: object) -> Conference:
    title = "Запад" if key == "west" else "Восток"
    parsed: list[TableRow] = []
    if isinstance(rows, list):
        for index, raw in enumerate(rows, start=1):
            if isinstance(raw, dict):
                parsed.append(_row(index, raw))
    return Conference(key, title, tuple(parsed))


def _row(rank: int, raw: dict) -> TableRow:
    club = club_from_api({"name": raw.get("name") or "", "location": raw.get("location") or ""}, side="home")
    return TableRow(
        rank=rank,
        name=club.name,
        city=club.city or str(raw.get("location") or ""),
        mark=club.mark,
        played=_num(raw.get("gp")),
        points=_num(raw.get("pts")),
        goals_for=_num(raw.get("gf")),
        goals_against=_num(raw.get("ga")),
        wins=_num(raw.get("w")),
        ot_wins=_num(raw.get("otw")),
        so_wins=_num(raw.get("sow")),
        so_losses=_num(raw.get("sol")),
        ot_losses=_num(raw.get("otl")),
        losses=_num(raw.get("l")),
        playoff=rank <= _PLAYOFF_PLACES,
    )


def _caption(tournament: str, stage: str, as_of: str, conferences: tuple[Conference, ...]) -> str:
    lines = [tournament, stage, as_of, ""]
    for conference in conferences:
        lines.append(conference.title)
        for row in conference.rows:
            lines.append(
                f"{row.rank}. {row.name} — {row.points} "
                f"({row.played} {_games(row.played)}, {row.goals_for}–{row.goals_against})"
            )
        lines.append("")
    if any(len(conference.rows) > _PLAYOFF_PLACES for conference in conferences):
        lines.append("Первые 8 мест конференции выходят в плей-офф.")
    return "\n".join(lines).strip()


def _tournament(season: str) -> str:
    parts = season.split("/")
    if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 4:
        return f"КХЛ · {parts[0][2:]}/{parts[1][2:]}"
    return f"КХЛ · {season}" if season else "КХЛ"


def _season_key(season: str) -> int:
    head = season.split("/", 1)[0]
    return int(head) if head.isdigit() else 0


def _num(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    return int(text) if text.lstrip("-").isdigit() else 0


def _games(count: int) -> str:
    rest = abs(count) % 100
    if 11 <= rest <= 14:
        return "игр"
    last = rest % 10
    if last == 1:
        return "игра"
    if 2 <= last <= 4:
        return "игры"
    return "игр"
