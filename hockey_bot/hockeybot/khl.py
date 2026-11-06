from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from hockeybot.models import Club, Footer, Goal, MatchCard
from hockeybot.teams import custom_club, find_clubs, normalize_name, resolve_club

MSK = timezone(timedelta(hours=3))
API_ROOT = "https://api-video.khl.ru/api/khl_site"
SITE_GAME = "https://www.khl.ru/game/{stage}/{game}/resume/"

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

# Короткие имена с сайта к длинным именам из палитры клубов.
_API_NAMES = {
    "динамо мн": "Динамо Минск",
    "динамо м": "Динамо Москва",
    "металлург мг": "Металлург",
    "хк сочи": "Сочи",
    "куньлунь рс": "Куньлунь Ред Стар",
    "куньлунь ред стар": "Куньлунь Ред Стар",
}

_DATE_RE = re.compile(
    r"(?:(?P<day>\d{1,2})(?:-?го)?\s+(?P<month>января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
    r"(?:\s+(?P<year>\d{4}))?"
    r"|(?P<d>\d{1,2})[./](?P<m>\d{1,2})(?:[./](?P<y>\d{2,4}))?)\s*$",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(r"^(?:матч|игра|встреча)\s+", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s+(?:—|–|-|против|vs)\s+", re.IGNORECASE)

Opener = Callable[[str, dict[str, Any]], Any]


class KhlError(Exception):
    pass


@dataclass(frozen=True)
class MatchRequest:
    left: str
    right: str
    day: date


@dataclass(frozen=True)
class ImportedMatch:
    card: MatchCard
    caption: str
    photo_url: str = ""
    played_at: datetime | None = None


def looks_like_khl_request(text: str) -> bool:
    return bool(_DATE_RE.search((text or "").strip()))


def parse_request(text: str, *, today: date | None = None) -> MatchRequest:
    raw = " ".join((text or "").split())
    match = _DATE_RE.search(raw)
    if not match:
        raise KhlError("Напиши два клуба и дату: Авангард ЦСКА 5 ноября 2026")
    teams = raw[: match.start()].strip(" ,.-—–")
    teams = _PREFIX_RE.sub("", teams).strip()
    left, right = _split_teams(teams)
    day = _request_date(match, today or datetime.now(MSK).date())
    return MatchRequest(left=left, right=right, day=day)


def load_match(text: str, *, today: date | None = None, opener: Opener | None = None) -> ImportedMatch:
    request = parse_request(text, today=today)
    fetch = opener or _open_json
    try:
        events = _events_on(request.day, fetch)
        brief = _choose_event(events, request)
        if brief.get("game_state_key") == "not_yet_started":
            raise KhlError(_not_started(brief, request.day))
        payload = fetch(f"{API_ROOT}/event_v2.json", {"id": brief["id"], "locale": "ru"})
    except KhlError:
        raise
    except Exception as exc:
        raise KhlError("Сайт КХЛ сейчас не отвечает. Попробуй ещё раз через минуту.") from exc
    event = payload.get("event") if isinstance(payload, dict) else None
    if not isinstance(event, dict):
        raise KhlError("КХЛ отдала протокол в неожиданном виде. Попробуй ещё раз.")
    return match_from_event(event)


def match_from_event(event: dict[str, Any]) -> ImportedMatch:
    home_raw = event.get("team_a") or {}
    away_raw = event.get("team_b") or {}
    if event.get("game_state_key") == "not_yet_started":
        stamp = event.get("event_start_at") or event.get("start_at") or 0
        played = datetime.fromtimestamp(stamp / 1000, tz=MSK).date() if stamp else date.today()
        raise KhlError(_not_started(event, played))
    home = club_from_api(home_raw, side="home")
    away = club_from_api(away_raw, side="away")
    home_score, away_score = _score_pair(event.get("score"))
    periods = period_lines(event.get("scores") or {}, event.get("goals") or [], home_raw.get("id"))
    goals = [_goal_from_api(item) for item in sorted(event.get("goals") or [], key=lambda item: item.get("time") or 0)]
    goals = [goal for goal in goals if goal is not None]
    played_on = datetime.fromtimestamp((event.get("event_start_at") or event.get("start_at") or 0) / 1000, tz=MSK)
    when = _russian_date(played_on.date())
    arena = _clean_arena((event.get("arena") or {}).get("name") or "")
    state = event.get("game_state_key") or ""
    overtime = bool((event.get("scores") or {}).get("overtime"))
    shootout = bool((event.get("scores") or {}).get("bullitt"))
    home_shots = _as_int(home_raw.get("shots"))
    away_shots = _as_int(away_raw.get("shots"))
    home_goalies = _goalies(home_raw, away_shots, away_score)
    away_goalies = _goalies(away_raw, home_shots, home_score)
    winner_goalies = home_goalies if home_score > away_score else away_goalies
    footer, note = _footer(winner_goalies, home_score, away_score, home_shots, away_shots, overtime, shootout, state)
    if state == "in_progress":
        note = "Матч ещё идёт"
    card = MatchCard(
        home=home,
        away=away,
        home_score=home_score,
        away_score=away_score,
        date=when,
        arena=arena,
        periods=periods,
        goals=goals,
        footer=footer,
        note=note,
        tournament=_tournament(event.get("season") or ""),
        kind="result",
    )
    caption = protocol_caption(
        card,
        year=played_on.year,
        overtime=overtime,
        shootout=shootout,
        home_shots=home_shots,
        away_shots=away_shots,
        home_goalies=home_goalies,
        away_goalies=away_goalies,
        penalties=_penalties(event.get("violations") or [], home_raw.get("id"), home.name, away.name),
        url=_game_url(event),
        live=state == "in_progress",
    )
    return ImportedMatch(
        card=card,
        caption=caption,
        photo_url=match_photo_url(event),
        played_at=played_on,
    )


def match_photo_url(event: dict[str, Any]) -> str:
    """Кадр решающей шайбы. Если клипа нет — общий кадр трансляции."""
    goals = sorted(event.get("goals") or [], key=lambda item: item.get("time") or 0)
    for goal in reversed(goals):
        url = str(((goal.get("quote") or {}).get("image_url") or "")).strip()
        if url.startswith("https://"):
            return url
    wide = str(event.get("image_big") or "").strip()
    if wide.startswith("https://"):
        return wide
    return ""


def period_lines(scores: dict[str, Any], goals: list[dict[str, Any]], home_id: Any) -> list[str]:
    parsed = _periods_from_scores(scores)
    if parsed and all(_period_ok(line) for line in parsed):
        return parsed
    return _periods_from_goals(goals, home_id)


def _is_exact_club(name: str) -> bool:
    hits = find_clubs(name)
    if len(hits) != 1:
        return False
    needle = normalize_name(name)
    club = hits[0]
    return needle == normalize_name(club.name) or needle in club.aliases


def club_key(name: str) -> str:
    query = _API_NAMES.get(normalize_name(name), name)
    hits = find_clubs(query)
    if len(hits) == 1:
        return normalize_name(hits[0].name)
    return normalize_name(query)


def club_from_api(team: dict[str, Any], *, side: str) -> Club:
    raw_name = str(team.get("name") or "").strip()
    query = _API_NAMES.get(normalize_name(raw_name), raw_name)
    club, options = resolve_club(query or raw_name or "Клуб", side=side)
    if options:
        club = custom_club(raw_name or query, side=side)
    city = club.city or str(team.get("location") or "")
    if city == club.city:
        return club
    return Club(club.name, city, club.mark, club.bar, club.bar_ink, club.aliases)


def protocol_caption(
    card: MatchCard,
    *,
    year: int,
    overtime: bool,
    shootout: bool,
    home_shots: int | None,
    away_shots: int | None,
    home_goalies: list[tuple[str, int | None]],
    away_goalies: list[tuple[str, int | None]],
    penalties: list[str],
    url: str,
    live: bool,
) -> str:
    score = f"{card.home_score}:{card.away_score}"
    if shootout:
        score += " Б"
    elif overtime:
        score += " ОТ"
    lines = [f"{card.home.name} — {card.away.name}", score, ""]
    when = " · ".join(part for part in (f"{card.date} {year}".strip(), card.arena) if part)
    if when:
        lines.append(when)
    if live:
        lines.append("Матч ещё идёт")
    if card.periods:
        lines.extend(["", "Периоды: " + ", ".join(card.periods)])
    if card.goals:
        lines.append("")
        lines.extend(_goal_line(goal) for goal in card.goals)
    extras: list[str] = []
    if home_shots is not None and away_shots is not None:
        extras.append(f"Броски в створ: {home_shots}–{away_shots}")
    goalies = _goalie_line(card.home.name, home_goalies, card.away.name, away_goalies)
    if goalies:
        extras.append(goalies)
    if penalties:
        extras.append("Удаления: " + "; ".join(penalties))
    if extras:
        lines.extend(["", *extras])
    if url:
        lines.extend(["", url])
    return "\n".join(lines).strip()


def _events_on(day: date, fetch: Opener) -> list[dict[str, Any]]:
    start, end = _day_bounds(day)
    payload = fetch(
        f"{API_ROOT}/events_v2.json",
        {
            "locale": "ru",
            "q[start_at_gt_time_from_unixtime]": start,
            "q[start_at_lt_time_from_unixtime]": end,
            "order_direction": "asc",
        },
    )
    rows = payload if isinstance(payload, list) else []
    events: list[dict[str, Any]] = []
    for row in rows:
        event = row.get("event") if isinstance(row, dict) else None
        if not isinstance(event, dict):
            continue
        # 24 — анонс и прямая трансляция, 18 — уже сыгранный матч в этом же календаре.
        if event.get("type_id") not in (None, 18, 24):
            continue
        if not event.get("team_a") or not event.get("team_b"):
            continue
        events.append(event)
    return _one_per_game(events)


def _one_per_game(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"finished": 2, "in_progress": 1, "not_yet_started": 0}
    chosen: dict[Any, dict[str, Any]] = {}
    for event in events:
        key = event.get("khl_id") or event.get("id")
        current = chosen.get(key)
        if current is None or rank.get(event.get("game_state_key"), 0) >= rank.get(current.get("game_state_key"), 0):
            chosen[key] = event
    return list(chosen.values())


def _choose_event(events: list[dict[str, Any]], request: MatchRequest) -> dict[str, Any]:
    wanted = {club_key(request.left), club_key(request.right)}
    found = []
    for event in events:
        keys = {club_key(event["team_a"].get("name") or ""), club_key(event["team_b"].get("name") or "")}
        if keys == wanted:
            found.append(event)
    if not found:
        raise KhlError(_missing(request, events))
    finished = [event for event in found if event.get("game_state_key") == "finished"]
    pool = finished or found
    pool.sort(key=lambda event: event.get("start_at") or 0)
    return pool[-1]


def _split_teams(text: str) -> tuple[str, str]:
    parts = [part.strip() for part in _SPLIT_RE.split(text) if part.strip()]
    if len(parts) == 2:
        return parts[0], parts[1]
    words = text.split()
    hits: list[tuple[str, str]] = []
    for index in range(1, len(words)):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        if _is_exact_club(left) and _is_exact_club(right):
            hits.append((left, right))
    if len(hits) == 1:
        return hits[0]
    if len(words) == 2:
        return words[0], words[1]
    raise KhlError("Не вижу два клуба. Пример: Авангард ЦСКА 5 ноября 2026")


def _request_date(match: re.Match[str], today: date) -> date:
    if match.group("day"):
        day = int(match.group("day"))
        month = _MONTHS[match.group("month").lower()]
        year = int(match.group("year")) if match.group("year") else None
    else:
        day = int(match.group("d"))
        month = int(match.group("m"))
        raw_year = match.group("y")
        year = int(raw_year) if raw_year else None
        if year is not None and year < 100:
            year += 2000
    if year is None:
        year = _nearest_year(day, month, today)
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise KhlError("Такой даты нет. Проверь число и месяц.") from exc


def _nearest_year(day: int, month: int, today: date) -> int:
    candidates: list[date] = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        raise KhlError("Такой даты нет. Проверь число и месяц.")
    return min(candidates, key=lambda item: abs((item - today).days)).year


def _periods_from_scores(scores: dict[str, Any]) -> list[str]:
    ends: list[tuple[int, int]] = []
    for key in ("first_period", "second_period", "third_period"):
        pair = _maybe_pair(scores.get(key))
        if pair is not None:
            ends.append(pair)
    if not ends:
        return []
    lines: list[str] = []
    previous = (0, 0)
    for end in ends:
        lines.append(f"{end[0] - previous[0]}:{end[1] - previous[1]}")
        previous = end
    for key in ("overtime", "bullitt"):
        current = _maybe_pair(scores.get(key))
        if current is None:
            continue
        if current[0] >= previous[0] and current[1] >= previous[1] and current != previous:
            lines.append(f"{current[0] - previous[0]}:{current[1] - previous[1]}")
            previous = current
        else:
            lines.append(f"{current[0]}:{current[1]}")
    return lines


def _periods_from_goals(goals: list[dict[str, Any]], home_id: Any) -> list[str]:
    buckets = {period: [0, 0] for period in range(1, 6)}
    seen = False
    for goal in goals:
        period = goal.get("period")
        if period not in buckets:
            continue
        side = 0 if (goal.get("author") or {}).get("team_id") == home_id else 1
        buckets[period][side] += 1
        seen = True
    if not seen:
        return []
    last = max(period for period, pair in buckets.items() if pair != [0, 0])
    return [f"{buckets[period][0]}:{buckets[period][1]}" for period in range(1, last + 1)]


def _goal_from_api(item: dict[str, Any]) -> Goal | None:
    author = item.get("author") or {}
    scorer = _surname(author.get("name") or "")
    if not scorer or item.get("time") is None:
        return None
    assists = ", ".join(
        name
        for name in (_surname(assist.get("name") or "") for assist in item.get("assistants") or [])
        if name
    )
    return Goal(
        time=_clock(int(item["time"])),
        scorer=scorer,
        assists=assists,
        tag=_goal_tag(str(item.get("status") or ""), str(item.get("status_abbr") or "")),
    )


def _goal_tag(status: str, abbr: str) -> str:
    text = normalize_name(f"{status} {abbr}")
    if "меньш" in text or abbr.lower() == "мен":
        return "мен"
    if "больш" in text or abbr.lower() in {"бол", "пп"}:
        return "бол"
    return ""


def _goalies(team: dict[str, Any], opponent_shots: int | None, opponent_goals: int) -> list[tuple[str, int | None]]:
    played: list[tuple[float, str]] = []
    for player in team.get("players") or []:
        if player.get("role_key") != "goaltender":
            continue
        seconds = _stat(player, "toi") or 0
        if seconds <= 0:
            continue
        surname = _surname(player.get("name") or "")
        if surname:
            played.append((seconds, surname))
    played.sort(reverse=True)
    if not played:
        return []
    saves = None
    if opponent_shots is not None and len(played) == 1:
        saves = max(opponent_shots - opponent_goals, 0)
    if len(played) == 1:
        return [(played[0][1], saves)]
    return [(name, None) for _, name in played]


def _footer(
    goalies: list[tuple[str, int | None]],
    home_score: int,
    away_score: int,
    home_shots: int | None,
    away_shots: int | None,
    overtime: bool,
    shootout: bool,
    state: str,
) -> tuple[Footer, str]:
    shutout = state == "finished" and (home_score == 0 or away_score == 0) and home_score != away_score
    if shutout and overtime:
        label, note = "Шатаут", "Сухой матч в овертайме"
    elif shutout:
        label, note = "Шатаут", "Сухой матч"
    elif shootout:
        label, note = "Буллиты", "Победа по буллитам"
    elif overtime:
        label, note = "Овертайм", "Победа в овертайме"
    else:
        label, note = "", ""
    if goalies:
        name, saves = goalies[0]
        center = f"{saves} {_saves_word(saves)}" if saves is not None else ""
        right = label
        right_sub = ""
        if not right and home_shots is not None and away_shots is not None:
            right = f"{home_shots}–{away_shots}"
            right_sub = "в створ"
        return Footer(name, center, right, "", "", right_sub), note
    if home_shots is not None and away_shots is not None:
        return Footer(f"{home_shots}–{away_shots}", "в створ", label), note
    return Footer(center=label) if label else Footer(), note


def _penalties(violations: list[dict[str, Any]], home_id: Any, home_name: str, away_name: str) -> list[str]:
    lines: list[str] = []
    for item in sorted(violations, key=lambda row: row.get("time") or 0):
        person = item.get("violator") or {}
        name = _surname(person.get("name") or "")
        if not name or item.get("time") is None:
            continue
        team = home_name if person.get("team_id") == home_id else away_name
        minutes = item.get("penalty_time") or ""
        reason = str(item.get("penalty_reason") or "").strip().lower()
        piece = f"{_clock(int(item['time']))} {name} ({team})"
        if minutes:
            piece += f", {minutes} мин"
        if reason:
            piece += f", {reason}"
        lines.append(piece)
    return lines


def _goal_line(goal: Goal) -> str:
    piece = f"{goal.time} {goal.scorer}"
    if goal.assists:
        piece += f" ({goal.assists})"
    if goal.tag:
        piece += f", {goal.tag}."
    return piece


def _goalie_line(
    home_name: str,
    home_goalies: list[tuple[str, int | None]],
    away_name: str,
    away_goalies: list[tuple[str, int | None]],
) -> str:
    bits = [_one_goalie(home_name, home_goalies), _one_goalie(away_name, away_goalies)]
    bits = [bit for bit in bits if bit]
    if not bits:
        return ""
    return "Вратари: " + "; ".join(bits)


def _one_goalie(team: str, goalies: list[tuple[str, int | None]]) -> str:
    if not goalies:
        return ""
    chunks = []
    for name, saves in goalies:
        if saves is None:
            chunks.append(f"{name} ({team})")
        else:
            chunks.append(f"{name} ({team}) — {saves} {_saves_word(saves)}")
    return ", ".join(chunks)


def _game_url(event: dict[str, Any]) -> str:
    stage = event.get("outer_stage_id")
    game = event.get("khl_id")
    if not stage or not game:
        return ""
    return SITE_GAME.format(stage=stage, game=game)


def _tournament(season: str) -> str:
    match = re.search(r"(\d{4})\s*/\s*(\d{4})", season or "")
    if not match:
        return "КХЛ"
    return f"КХЛ · {match.group(1)[2:]}/{match.group(2)[2:]}"


def _missing(request: MatchRequest, events: list[dict[str, Any]]) -> str:
    when = _russian_date(request.day)
    if not events:
        return f"На {when} {request.day.year} в календаре КХЛ нет матчей."
    slate = []
    for event in events[:12]:
        home = (event.get("team_a") or {}).get("name") or "?"
        away = (event.get("team_b") or {}).get("name") or "?"
        score = event.get("score") or "–:–"
        slate.append(f"{home} — {away} {score}")
    played = "\n".join(slate)
    return (
        f"На {when} {request.day.year} игры {request.left} — {request.right} нет.\n"
        f"В этот день КХЛ сыграла:\n{played}"
    )


def _not_started(event: dict[str, Any], day: date) -> str:
    home = (event.get("team_a") or {}).get("name") or "Хозяева"
    away = (event.get("team_b") or {}).get("name") or "гости"
    stamp = event.get("start_at") or event.get("event_start_at")
    clock = ""
    if stamp:
        clock = datetime.fromtimestamp(stamp / 1000, tz=MSK).strftime("%H:%M")
    when = _russian_date(day)
    tail = f", начало в {clock} мск" if clock else ""
    return f"Матч ещё не начался: {home} — {away}, {when}{tail}."


def _russian_date(day: date) -> str:
    month = next(name for name, number in _MONTHS.items() if number == day.month)
    return f"{day.day} {month}"


def _day_bounds(day: date) -> tuple[int, int]:
    start = datetime(day.year, day.month, day.day, tzinfo=MSK)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _score_pair(value: Any) -> tuple[int, int]:
    pair = _maybe_pair(value)
    if pair is None:
        return 0, 0
    return pair


def _period_ok(line: str) -> bool:
    pair = _maybe_pair(line)
    return pair is not None and pair[0] >= 0 and pair[1] >= 0


def _maybe_pair(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    left, right = value.split(":", 1)
    if not left.strip().isdigit() or not right.strip().isdigit():
        return None
    return int(left), int(right)


def _clock(seconds: int) -> str:
    minutes, rest = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{rest:02d}"


def _surname(name: str) -> str:
    parts = name.split()
    return parts[0] if parts else ""


def _stat(player: dict[str, Any], stat_id: str) -> float | None:
    for item in player.get("match_stats") or []:
        if item.get("id") == stat_id:
            try:
                return float(item.get("val"))
            except (TypeError, ValueError):
                return None
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _saves_word(count: int) -> str:
    rest = abs(count) % 100
    if 11 <= rest <= 14:
        return "сейвов"
    last = rest % 10
    if last == 1:
        return "сейв"
    if 2 <= last <= 4:
        return "сейва"
    return "сейвов"


def _clean_arena(name: str) -> str:
    return name.replace("«", "").replace("»", "").replace('"', "").strip()


def _open_json(url: str, params: dict[str, Any]) -> Any:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "hockey-poster-bot/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise KhlError("Сайт КХЛ сейчас не отвечает. Попробуй ещё раз через минуту.") from exc
