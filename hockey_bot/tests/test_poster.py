import struct
from pathlib import Path

from hockeybot.models import Club, Footer, Goal, MatchCard
from hockeybot.poster import render_poster
from hockeybot.templates_lib import demo_card


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


def test_type_poster_has_feed_size(tmp_path: Path) -> None:
    dest = tmp_path / "type.png"
    render_poster(demo_card(), dest)
    assert _png_size(dest) == (2160, 2700)


def test_announce_and_photo_posters(tmp_path: Path) -> None:
    announce = demo_card()
    announce.kind = "announce"
    announce.home_score = None
    announce.away_score = None
    announce.goals = []
    announce.footer = Footer()
    render_poster(announce, tmp_path / "announce.png")

    photo = _huddle()
    if photo is None:
        return
    card = demo_card()
    card.photo_path = str(photo)
    card.goals = [
        Goal("03:33", "Родуолд", "Кулик, Ремпал"),
        Goal("15:02", "Жаровский", "Загребин, Кулик"),
        Goal("30:41", "Загребин", "Маджио, Варлов"),
        Goal("50:14", "Ремпал", "Родуолд", "мен"),
        Goal("55:43", "Ремпал", "Жаровский, Цулыгин", "бол"),
    ]
    card.note = "Серия из трёх поражений прервана\n6-е место Востока · 23 очка"
    render_poster(card, tmp_path / "photo.png")
    assert _png_size(tmp_path / "photo.png") == (2160, 2700)


def test_unknown_club_colors_still_render(tmp_path: Path) -> None:
    card = MatchCard(
        home=Club("Северные", "", "#d6ff3c", "#d6ff3c", "#0a1408"),
        away=Club("Южные", "Город", "#8eb6ee", "#1e4e96", "#f4f7ef"),
        home_score=2,
        away_score=1,
        date="5 ноября",
        tournament="КХЛ · 26/27",
    )
    render_poster(card, tmp_path / "plain.png")
    assert _png_size(tmp_path / "plain.png") == (2160, 2700)


def _huddle() -> Path | None:
    candidate = Path("/tmp/salavat-poster/huddle.jpg")
    return candidate if candidate.is_file() else None
