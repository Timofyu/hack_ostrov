from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from PIL import ImageFont

from hockeybot.khl import KhlError, MSK, _russian_date, club_from_api, games_on

_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONTS: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_INNER_WIDTH = 960

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
    title: str
    games: tuple[DayGame, ...]
    caption: str


def load_day(day: date, *, opener=None, results: bool = False) -> DaySlate:
    events = games_on(day, opener=opener)
    if not events:
        raise KhlError(f"На {_russian_date(day)} {day.year} в календаре КХЛ нет матчей.")
    games = tuple(_game(event) for event in events)
    stage = str(events[0].get("stage_name") or "")
    tournament = _tournament(stage)
    label = _russian_date(day)
    title = "Итоги дня" if results else "Превью дня"
    caption = _results_caption(label, day.year, games) if results else _caption(tournament, label, day.year, games)
    return DaySlate(
        tournament=tournament,
        date_label=label,
        year=day.year,
        title=title,
        games=games,
        caption=caption,
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


def _results_caption(label: str, year: int, games: tuple[DayGame, ...]) -> str:
    lines = ["Итоги дня", f"{label} {year}", ""]
    for game in games:
        if game.score:
            live = " · идёт" if game.live else ""
            lines.append(f"{game.home} {game.score} {game.away}{live}")
        else:
            lines.append(f"{game.time} {game.home} — {game.away}".strip())
    return "\n".join(lines).strip()


def _tournament(stage_name: str) -> str:
    match = re.search(r"(\d{4})\s*/\s*(\d{4})", stage_name or "")
    if not match:
        return "КХЛ"
    return f"КХЛ · {match.group(1)[2:]}/{match.group(2)[2:]}"


def day_scale(names: list[str], count: int) -> dict[str, int]:
    """Размер эмблем и шрифта под число матчей и самое длинное имя."""
    count = min(max(count, 1), 12)
    labels = [name.strip().upper() for name in names if name and name.strip()] or ["КХЛ"]
    title = _clamp(78 - max(count - 2, 0) * 5, 42, 72)
    row = (1350 - 68 - 48 - title - 28) / count
    gap = 12 if count >= 7 else 18
    base_crest = _clamp(round(row * 0.5), 44, 136)
    base_name = _clamp(round(row * 0.17), 22, 52)
    base_clock = _clamp(round(row * 0.15), 26, 48)
    base_score = _clamp(round(row * 0.23), 32, 84)

    def pack(scale: float) -> tuple[int, int, int, int]:
        name = max(17, round(base_name * scale))
        crest = max(34, round(base_crest * scale))
        crest = min(crest, round(row * 0.58), name * 3 + 6)
        clock = max(22, round(base_clock * scale))
        score = max(26, round(base_score * scale))
        return crest, name, clock, score

    best = pack(0.35)
    low, high = 0.35, 1.0
    for _ in range(14):
        mid = (low + high) / 2
        trial = pack(mid)
        if _line_fits(labels, row, *trial, gap):
            best = trial
            low = mid
        else:
            high = mid
    crest, name, clock, score = best
    return {
        "crest": crest,
        "name": name,
        "city": _clamp(round(name * 0.44), 12, 18),
        "score": score,
        "time": clock,
        "title": title,
        "gap": gap,
    }


def _line_fits(
    labels: list[str],
    row: float,
    crest: int,
    name: int,
    clock: int,
    score: int,
    gap: int,
) -> bool:
    name_w = max(_text_width(label, name, "Inter-Bold.ttf") for label in labels)
    time_w = _text_width("19:30", clock, "Unbounded.ttf")
    score_w = _text_width("10:10", score, "Unbounded.ttf")
    city = max(12, round(name * 0.44))
    block = max(crest, name + 8 + city)
    total = time_w + score_w + 2 * (crest + gap + name_w) + gap * 3
    return total <= _INNER_WIDTH and block <= row - 20


def _text_width(text: str, size: int, face: str) -> int:
    key = (face, size)
    font = _FONTS.get(key)
    if font is None:
        font = ImageFont.truetype(str(_FONT_DIR / face), size)
        _FONTS[key] = font
    box = font.getbbox(text)
    return box[2] - box[0]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _clock(stamp: object) -> str:
    if not isinstance(stamp, (int, float)) or stamp <= 0:
        return ""
    seconds = stamp / 1000 if stamp > 10**12 else stamp
    return datetime.fromtimestamp(seconds, tz=MSK).strftime("%H:%M")
