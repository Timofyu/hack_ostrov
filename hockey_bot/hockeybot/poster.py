from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from hockeybot.models import Club, Footer, Goal, MatchCard

ASSETS = Path(__file__).resolve().parent / "assets"
FONTS = ASSETS / "fonts"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_PERIOD_LABELS = ("I", "II", "III", "ОТ")

_ENV = Environment(
    loader=FileSystemLoader(ASSETS),
    autoescape=select_autoescape(["html"]),
)


class PosterError(RuntimeError):
    pass


def render_poster(card: MatchCard, dest: Path, chrome_path: str | None = None) -> Path:
    chrome = chrome_path or find_chrome()
    if not chrome:
        raise PosterError(
            "Не найден Chrome. Поставь Google Chrome или укажи путь в CHROME_PATH."
        )
    missing = [name for name in ("Unbounded.ttf", "Inter-Regular.ttf", "Inter-Bold.ttf") if not (FONTS / name).exists()]
    if missing:
        raise PosterError("В комплекте бота не хватает шрифтов: " + ", ".join(missing))

    view = build_view(card)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hockey-poster-") as tmp_name:
        tmp = Path(tmp_name)
        (tmp / "fonts").symlink_to(FONTS)
        if card.photo_path:
            source = Path(card.photo_path)
            if not source.is_file():
                raise PosterError("Файл фото не найден. Пришли кадр ещё раз.")
            suffix = source.suffix.lower() if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"
            photo_name = f"photo{suffix}"
            shutil.copy(source, tmp / photo_name)
            view["photo_name"] = photo_name
        html = _ENV.get_template("poster.html").render(**view)
        (tmp / "index.html").write_text(html, encoding="utf-8")
        png = tmp / "poster.png"
        _screenshot(tmp / "index.html", png, chrome)
        dest.write_bytes(png.read_bytes())
    return dest


def build_view(card: MatchCard) -> dict:
    mode = _mode(card)
    counts = Counter(goal.scorer for goal in card.goals)
    hot = {name for name, count in counts.items() if count >= 2}
    headline, headline_sub = goal_headline(card.goals)
    periods = []
    for index, period in enumerate(card.periods[:4]):
        left, _, right = period.partition(":")
        periods.append(
            {
                "label": _PERIOD_LABELS[index] if index < len(_PERIOD_LABELS) else "ОТ",
                "home": left,
                "away": right,
            }
        )
    footer_cells, footer_single = _footer_cells(card.footer)
    home_lines = name_lines(card.home.name)
    away_lines = name_lines(card.away.name)
    wide_score = bool(
        (card.home_score is not None and card.home_score >= 10)
        or (card.away_score is not None and card.away_score >= 10)
    )
    return {
        "mode": mode,
        "dense": len(card.goals) >= 6,
        "tournament": card.tournament or "КХЛ · 26/27",
        "when_chip": " · ".join(part for part in (card.date, card.arena) if part),
        "date": card.date,
        "arena": card.arena,
        "home_lines": home_lines,
        "away_lines": away_lines,
        "home_size": name_size(home_lines),
        "away_size": name_size(away_lines),
        "home_city": card.home.city,
        "away_city": card.away.city,
        "away_name": card.away.name,
        "home_score": card.home_score,
        "away_score": card.away_score,
        "wide_score": wide_score,
        "periods": periods,
        "goals": [
            {
                "time": goal.time,
                "scorer": goal.scorer,
                "assists": goal.assists,
                "tag": goal.tag,
                "hot": goal.scorer in hot,
            }
            for goal in card.goals
        ],
        "goal_count": len(card.goals),
        "note": card.note.strip(),
        "headline": headline,
        "headline_sub": headline_sub,
        "footer_cells": footer_cells,
        "footer_single": footer_single,
        "accent": _hex(card.home.mark, "#d6ff3c"),
        "away": _hex(card.away.mark, "#8eb6ee"),
        "bar": _hex(card.home.bar, "#d6ff3c"),
        "bar_ink": _hex(card.home.bar_ink, "#0a1408"),
        "photo_name": "",
        "guest_line": " · ".join(part for part in (card.away.name, card.away.city) if part),
    }


def goal_headline(goals: list[Goal]) -> tuple[str, str]:
    if not goals:
        return "", ""
    counts = Counter(goal.scorer for goal in goals)
    name = max(counts, key=lambda scorer: (counts[scorer], -_first_index(goals, scorer)))
    count = counts[name]
    if count < 2:
        return "", ""
    titles = {2: "дубль", 3: "хет-трик", 4: "покер"}
    title = titles.get(count, f"{count} шайбы")
    tags: list[str] = []
    for goal in goals:
        if goal.scorer != name:
            continue
        if goal.tag == "мен" and "меньшинство" not in tags:
            tags.append("меньшинство")
        elif goal.tag == "бол" and "большинство" not in tags:
            tags.append("большинство")
    return f"{name} · {title}", " и ".join(tags)


def name_lines(name: str) -> list[str]:
    parts = name.split()
    if len(parts) >= 2 and len(name) > 9:
        if len(parts) == 2:
            return parts
        return [" ".join(parts[:-1]), parts[-1]]
    return [name or "Команда"]


def name_size(lines: list[str]) -> str:
    longest = max(len(line) for line in lines)
    if longest >= 16:
        return "sm"
    if longest >= 12:
        return "md"
    return "lg"


def find_chrome() -> str | None:
    configured = os.environ.get("CHROME_PATH", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(
        [
            "/opt/google/chrome/chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _mode(card: MatchCard) -> str:
    photo = "photo" if card.photo_path else "type"
    kind = "announce" if card.kind == "announce" else "result"
    return f"{photo}-{kind}"


def _footer_cells(footer: Footer) -> tuple[list[dict[str, str]], bool]:
    cells = [
        {"text": footer.left, "sub": footer.left_sub},
        {"text": footer.center, "sub": footer.center_sub},
        {"text": footer.right, "sub": footer.right_sub},
    ]
    filled = [cell for cell in cells if cell["text"] or cell["sub"]]
    if not filled:
        return [], True
    if len(filled) == 1:
        return filled, True
    return cells, False


def _first_index(goals: list[Goal], scorer: str) -> int:
    for index, goal in enumerate(goals):
        if goal.scorer == scorer:
            return index
    return 0


def _hex(value: str, fallback: str) -> str:
    if _HEX.match(value or ""):
        return value
    return fallback


def _screenshot(html_path: Path, png_path: Path, chrome: str) -> None:
    profile = html_path.parent / "profile"
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        f"--user-data-dir={profile}",
        "--force-device-scale-factor=2",
        "--window-size=1080,1350",
        "--virtual-time-budget=8000",
        f"--screenshot={png_path}",
        html_path.as_uri(),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    if not png_path.exists() or png_path.stat().st_size < 5000:
        raise PosterError("Chrome не собрал превью. Попробуй ещё раз.")
