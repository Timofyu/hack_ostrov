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
_PERIOD_LABELS = ("I", "II", "III", "ОТ", "Б")

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
            "Не нашёл браузер, которым можно собрать картинку. "
            "Подойдёт Chrome, Edge, Яндекс Браузер, Brave, Opera или Firefox. "
            "Если браузер установлен, укажи путь к нему в BROWSER_PATH."
        )
    missing = [name for name in ("Unbounded.ttf", "Inter-Regular.ttf", "Inter-Bold.ttf") if not (FONTS / name).exists()]
    if missing:
        raise PosterError("В комплекте бота не хватает шрифтов: " + ", ".join(missing))

    view = build_view(card)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hockey-poster-") as tmp_name:
        tmp = Path(tmp_name)
        _link_fonts(tmp / "fonts")
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


def _link_fonts(destination: Path) -> None:
    try:
        destination.symlink_to(FONTS, target_is_directory=True)
    except OSError:
        shutil.copytree(FONTS, destination)


def build_view(card: MatchCard) -> dict:
    mode = _mode(card)
    counts = Counter(goal.scorer for goal in card.goals)
    hot = {name for name, count in counts.items() if count >= 2}
    headline, headline_sub = goal_headline(card.goals)
    periods = []
    for index, period in enumerate(card.periods[:5]):
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
    """Ищет любой браузер, которым можно снять превью. Chrome не обязателен."""
    for candidate in _browser_candidates():
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def browser_family(path: str) -> str:
    name = Path(path).name.lower()
    if "firefox" in name:
        return "firefox"
    return "chromium"


def _browser_candidates() -> list[str]:
    configured: list[str] = []
    for key in ("BROWSER_PATH", "CHROME_PATH"):
        value = os.environ.get(key, "").strip().strip('"')
        if value:
            configured.append(value)
    on_path: list[str] = []
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "microsoft-edge-stable",
        "msedge",
        "brave-browser",
        "brave",
        "yandex-browser",
        "opera",
        "firefox",
        "firefox-esr",
    ):
        found = shutil.which(name)
        if found:
            on_path.append(found)
    # Сначала обычные установки. Обёртки из PATH иногда добавляют отладчик и не завершаются.
    return configured + _known_browser_paths() + on_path


def _known_browser_paths() -> list[str]:
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    program = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    paths = [
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
        "/usr/bin/brave-browser",
        "/usr/bin/yandex-browser",
        "/usr/bin/opera",
        "/usr/bin/firefox",
        "/snap/bin/firefox",
        "/snap/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Yandex.app/Contents/MacOS/Yandex",
        "/Applications/Opera.app/Contents/MacOS/Opera",
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        str(Path(program) / "Google/Chrome/Application/chrome.exe"),
        str(Path(program_x86) / "Google/Chrome/Application/chrome.exe"),
        str(Path(local) / "Google/Chrome/Application/chrome.exe") if local else "",
        str(home / "AppData/Local/Google/Chrome/Application/chrome.exe"),
        str(Path(program) / "Microsoft/Edge/Application/msedge.exe"),
        str(Path(program_x86) / "Microsoft/Edge/Application/msedge.exe"),
        str(Path(program) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        str(Path(local) / "Yandex/YandexBrowser/Application/browser.exe") if local else "",
        str(home / "AppData/Local/Yandex/YandexBrowser/Application/browser.exe"),
        str(Path(program) / "Mozilla Firefox/firefox.exe"),
        str(Path(program_x86) / "Mozilla Firefox/firefox.exe"),
        str(Path(local) / "Programs/Opera/opera.exe") if local else "",
    ]
    return [path for path in paths if path]


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


def _screenshot(html_path: Path, png_path: Path, browser: str) -> None:
    profile = html_path.parent / "profile"
    if browser_family(browser) == "firefox":
        commands = [_firefox_command(browser, html_path, png_path, profile)]
    else:
        commands = [
            _chromium_command(browser, html_path, png_path, profile / "new", headless="--headless=new"),
            _chromium_command(browser, html_path, png_path, profile / "classic", headless="--headless"),
        ]
    for command, env in commands:
        if png_path.exists():
            png_path.unlink()
        _run_browser(command, env)
        if png_path.exists() and png_path.stat().st_size >= 5000:
            return
    raise PosterError("Браузер не собрал превью. Попробуй ещё раз.")


def _chromium_command(
    browser: str,
    html_path: Path,
    png_path: Path,
    profile: Path,
    *,
    headless: str,
) -> tuple[list[str], dict[str, str]]:
    command = [
        browser,
        headless,
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
    return command, os.environ.copy()


def _firefox_command(
    browser: str,
    html_path: Path,
    png_path: Path,
    profile: Path,
) -> tuple[list[str], dict[str, str]]:
    command = [
        browser,
        "--headless",
        "--profile",
        str(profile),
        "--screenshot",
        str(png_path),
        html_path.as_uri(),
    ]
    env = os.environ.copy()
    env["MOZ_HEADLESS"] = "1"
    env["MOZ_HEADLESS_WIDTH"] = "1080"
    env["MOZ_HEADLESS_HEIGHT"] = "1350"
    return command, env


def _run_browser(command: list[str], env: dict[str, str]) -> None:
    if os.name == "nt":
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
