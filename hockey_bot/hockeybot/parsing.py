from __future__ import annotations

import re

from hockeybot.models import Footer, Goal

class ParseError(ValueError):
    pass


_TAG_MAP = {
    "мен": "мен",
    "меньш": "мен",
    "меньшинстве": "мен",
    "меньшинство": "мен",
    "sh": "мен",
    "бол": "бол",
    "больш": "бол",
    "большинстве": "бол",
    "большинство": "бол",
    "pp": "бол",
    "пп": "бол",
}


def parse_score(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d{1,2})\s*[:\-–]\s*(\d{1,2})\s*", text or "")
    if not match:
        raise ParseError("Нужен счёт вроде 5:0 — сначала шайбы хозяев.")
    return int(match.group(1)), int(match.group(2))


def parse_when(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        raise ParseError("Напиши дату и арену, например: 4 ноября · Уфа-Арена")
    for sep in (" · ", " | ", "\n"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            return _clean(left), _clean(right)
    if "," in raw:
        left, right = raw.split(",", 1)
        return _clean(left), _clean(right)
    return _clean(raw), ""


def parse_periods(text: str) -> list[str]:
    parts = [part for part in re.split(r"[,;\s]+", (text or "").strip()) if part]
    if not parts or len(parts) > 4:
        raise ParseError("Периоды пиши так: 2:0, 1:0, 2:0")
    periods: list[str] = []
    for part in parts:
        match = re.fullmatch(r"(\d{1,2})\s*[:\-–]\s*(\d{1,2})", part)
        if not match:
            raise ParseError("Периоды пиши так: 2:0, 1:0, 2:0")
        periods.append(f"{int(match.group(1))}:{int(match.group(2))}")
    return periods


def parse_goals(text: str) -> list[Goal]:
    lines = [_strip_bullet(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise ParseError("Пришли хотя бы одну шайбу.")
    if len(lines) > 14:
        raise ParseError("Для превью хватит 14 шайб. Остальное уйдёт в текст поста.")
    goals: list[Goal] = []
    for index, line in enumerate(lines, start=1):
        try:
            goals.append(parse_goal_line(line))
        except ParseError as exc:
            raise ParseError(f"Строка {index}: {exc}") from exc
    return goals


def parse_goal_line(line: str) -> Goal:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})\s+(.+)", line.strip())
    if not match:
        raise ParseError("строка должна начинаться со времени, например 12:04 Иванов — Петров.")
    minute = int(match.group(1))
    second = int(match.group(2))
    if minute > 99 or second > 59:
        raise ParseError("проверь время шайбы.")
    rest = match.group(3).strip()
    tag = ""
    if "|" in rest:
        body, raw_tag = rest.rsplit("|", 1)
        tag = _normalize_tag(raw_tag)
        rest = body.strip()
    scorer, assists = _split_scorer(rest)
    if not scorer:
        raise ParseError("не вижу автора шайбы.")
    return Goal(time=f"{minute:02d}:{second:02d}", scorer=scorer, assists=assists, tag=tag)


def parse_footer(text: str) -> Footer:
    lines = [_clean(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise ParseError("Плашка пустая. Пример: Бочаров | 33 сейва | Шатаут")
    main = _split_footer_line(lines[0])
    subs = _split_footer_line(lines[1]) if len(lines) > 1 else ["", "", ""]
    filled = [part for part in main if part]
    if len(filled) == 1 and not any(subs):
        return Footer(center=filled[0])
    main = (main + ["", "", ""])[:3]
    subs = (subs + ["", "", ""])[:3]
    return Footer(main[0], main[1], main[2], subs[0], subs[1], subs[2])


def parse_quick(text: str) -> dict:
    lines = [_strip_bullet(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < 2:
        raise ParseError(
            "Нужны хотя бы две строки:\nСалават Юлаев — Лада\n5:0"
        )
    home_name, away_name = _split_teams(lines[0])
    home_score, away_score = parse_score(lines[1])
    index = 2
    date, arena = "", ""
    periods: list[str] = []
    if index < len(lines) and not _is_periods(lines[index]) and not _is_goal(lines[index]) and not _is_footer(lines[index]):
        date, arena = parse_when(lines[index])
        index += 1
    if index < len(lines) and _is_periods(lines[index]):
        periods = parse_periods(lines[index])
        index += 1
    goals: list[Goal] = []
    while index < len(lines) and _is_goal(lines[index]):
        goals.append(parse_goal_line(lines[index]))
        index += 1
    footer = Footer()
    if index < len(lines) and _is_footer(lines[index]):
        chunk = lines[index]
        index += 1
        if index < len(lines) and _is_footer(lines[index]):
            chunk = chunk + "\n" + lines[index]
            index += 1
        footer = parse_footer(chunk)
    note = "\n".join(lines[index:]).strip()
    if len(note) > 400:
        raise ParseError("Сноска длиннее 400 знаков. Сократи её.")
    return {
        "home_name": home_name,
        "away_name": away_name,
        "home_score": home_score,
        "away_score": away_score,
        "date": date,
        "arena": arena,
        "periods": periods,
        "goals": goals,
        "footer": footer,
        "note": note,
    }


def _split_teams(line: str) -> tuple[str, str]:
    for sep in (" — ", " – ", " - ", "—", "–"):
        if sep in line:
            left, right = line.split(sep, 1)
            if left.strip() and right.strip():
                return _clean(left), _clean(right)
    raise ParseError("Первая строка должна быть такой: Салават Юлаев — Лада")


def _split_scorer(rest: str) -> tuple[str, str]:
    paren = re.fullmatch(r"(.+?)\s*\((.+)\)\s*", rest)
    if paren:
        return _clean(paren.group(1)), _clean(paren.group(2))
    for sep in (" — ", " – ", " - "):
        if sep in rest:
            left, right = rest.split(sep, 1)
            return _clean(left), _clean(right)
    return _clean(rest), ""


def _normalize_tag(raw: str) -> str:
    token = normalize_tag_key(raw)
    if not token:
        return ""
    if token not in _TAG_MAP:
        raise ParseError("пометку шайбы пиши как мен или бол.")
    return _TAG_MAP[token]


def normalize_tag_key(raw: str) -> str:
    token = raw.lower().replace("ё", "е").strip(" .")
    token = token.removeprefix("в ").strip()
    return token


def _split_footer_line(line: str) -> list[str]:
    if "|" in line:
        return [_clean(part) for part in line.split("|")]
    if "·" in line:
        return [_clean(part) for part in line.split("·")]
    return [_clean(line)]


def _is_periods(line: str) -> bool:
    parts = [part for part in re.split(r"[,;\s]+", line.strip()) if part]
    if not 1 <= len(parts) <= 4:
        return False
    return all(re.fullmatch(r"\d{1,2}[:\-–]\d{1,2}", part) for part in parts)


def _is_goal(line: str) -> bool:
    return bool(re.match(r"^\d{1,2}:\d{2}\s+\S", line.strip()))


def _is_footer(line: str) -> bool:
    return "|" in line and not _is_goal(line)


def _strip_bullet(line: str) -> str:
    return re.sub(r"^[-•*]\s+", "", line.strip())


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .")
