from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape

from hockeybot.models import Club
from hockeybot.teams import normalize_name

log = logging.getLogger(__name__)

# Официальные телеграм-каналы клубов. Публичная лента t.me/s/ отдаёт фото без входа в аккаунт.
CHANNELS: dict[str, str] = {
    "Салават Юлаев": "hcsu61",
    "Лада": "hc_lada",
    "Ак Барс": "hc_akbars",
    "Авангард": "omskiyavangard",
    "ЦСКА": "cska_hockey",
    "СКА": "hcska",
    "Динамо Москва": "dynamo_ru",
    "Динамо Минск": "hcminsk",
    "Локомотив": "hclokomotiv_official",
    "Металлург": "metallurgmgn",
    "Автомобилист": "hc_avtomobilist",
    "Трактор": "hctraktor",
    "Спартак": "hc_spartak",
    "Торпедо": "torpedonn",
    "Нефтехимик": "hcneftekhimik",
    "Барыс": "barys_hc",
    "Адмирал": "hcadmiralru",
    "Амур": "hcamur1957",
    "Витязь": "hc_vityaz_khl",
    "Северсталь": "hcseverstal",
    "Сибирь": "hockeyclubsibir",
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ChannelPost:
    post_id: int
    published: datetime
    text: str
    photos: tuple[str, ...]


def find_social_photos(home: Club, away: Club, played_at: datetime) -> list[str]:
    """Фото с официальных каналов хозяев и гостей вокруг времени матча."""
    if played_at.tzinfo is None:
        played_at = played_at.replace(tzinfo=timezone.utc)
    ranked: list[tuple[int, ChannelPost]] = []
    for club, opponent in ((home, away), (away, home)):
        channel = CHANNELS.get(club.name)
        if not channel:
            continue
        try:
            posts = _load_channel(channel, played_at)
        except Exception:
            log.warning("Не прочитал канал %s", channel, exc_info=True)
            continue
        chosen = choose_post(posts, opponent, played_at)
        if chosen is not None:
            # Альбом хозяев важнее одиночной карточки гостей: там живые кадры матча.
            bonus = 3 if club is home else 0
            ranked.append((score_post(chosen, opponent, played_at) + bonus, chosen))
    if not ranked:
        return []
    ranked.sort(key=lambda item: item[0], reverse=True)
    return list(ranked[0][1].photos[:6])


def choose_post(posts: list[ChannelPost], opponent: Club, played_at: datetime) -> ChannelPost | None:
    best: ChannelPost | None = None
    best_score = 0
    for post in posts:
        current = score_post(post, opponent, played_at)
        if current > best_score:
            best = post
            best_score = current
    return best


def score_post(post: ChannelPost, opponent: Club, played_at: datetime) -> int:
    if not post.photos:
        return 0
    if played_at.tzinfo is None:
        played_at = played_at.replace(tzinfo=timezone.utc)
    published = post.published
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    if not played_at - timedelta(hours=3) <= published <= played_at + timedelta(hours=36):
        return 0
    text = normalize_name(post.text)
    score = 1
    if _mentions(text, opponent):
        score += 4
    if len(post.photos) >= 4:
        score += 6
    if any(word in text for word in ("фото", "галере", "альбом")):
        score += 2
    if any(word in text for word in ("побед", "одержал", "сухар", "шайб")):
        score += 2
    hours = (published - played_at).total_seconds() / 3600
    if -2 <= hours <= 8:
        score += 2
    return score


def parse_telegram_channel(html: str) -> list[ChannelPost]:
    posts: list[ChannelPost] = []
    for block in re.split(r'<div class="tgme_widget_message ', html)[1:]:
        ident = re.search(r'data-post="[^"/]+/(\d+)"', block)
        stamp = re.search(r'datetime="([^"]+)"', block)
        if not ident or not stamp:
            continue
        text_match = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        text = ""
        if text_match:
            text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text_match.group(1)))).strip()
        photos: list[str] = []
        for raw in re.findall(r"message_photo_wrap[\s\S]{0,700}?background-image:url\('([^']+)'\)", block):
            url = raw if raw.startswith("http") else "https:" + raw
            if "telesco.pe" not in url and "telegram-cdn" not in url:
                continue
            if url not in photos:
                photos.append(url)
        try:
            published = datetime.fromisoformat(stamp.group(1))
        except ValueError:
            continue
        posts.append(ChannelPost(int(ident.group(1)), published, text, tuple(photos)))
    return posts


def _mentions(text: str, club: Club) -> bool:
    needles = [normalize_name(club.name), *(normalize_name(alias) for alias in club.aliases)]
    return any(len(needle) >= 3 and needle in text for needle in needles)


def _load_channel(username: str, played_at: datetime) -> list[ChannelPost]:
    if not re.fullmatch(r"[A-Za-z0-9_]{4,64}", username):
        return []
    window_start = played_at - timedelta(hours=3)
    collected: list[ChannelPost] = []
    before: int | None = None
    for _ in range(8):
        url = f"https://t.me/s/{username}"
        if before is not None:
            url += f"?before={before}"
        page = parse_telegram_channel(_fetch(url))
        if not page:
            break
        collected.extend(page)
        oldest = min(post.published for post in page)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        if oldest <= window_start:
            break
        next_before = min(post.post_id for post in page)
        if before is not None and next_before >= before:
            break
        before = next_before
    return collected


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc
