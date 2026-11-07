from __future__ import annotations

import re

from hockeybot.models import Club

# mark — цвет цифры и акцентов на чёрном.
# bar — плашка внизу, bar_ink — текст на ней.
_CLUBS: tuple[Club, ...] = (
    Club("Салават Юлаев", "Уфа", "#d6ff3c", "#d6ff3c", "#0a1408", ("салават", "салават юлаев", "юлаев")),
    Club("Лада", "Тольятти", "#8eb6ee", "#1e4e96", "#f4f7ef", ("лада", "лада тольятти")),
    Club("Ак Барс", "Казань", "#b6ff5c", "#0b8f45", "#f4f7ef", ("ак барс", "акбарс", "барс")),
    Club("Авангард", "Омск", "#ff6a52", "#e10600", "#fff7f4", ("авангард",)),
    Club("ЦСКА", "Москва", "#ff6b78", "#c8102e", "#fff7f4", ("цска", "цска москва")),
    Club("СКА", "Санкт-Петербург", "#8eb6ff", "#003da5", "#f4f7ef", ("ска", "ска спб")),
    Club("Динамо Москва", "Москва", "#8eb6ff", "#1a4f9c", "#f4f7ef", ("динамо москва", "динамо м", "динамо мск")),
    Club("Динамо Минск", "Минск", "#7ec8ff", "#0a6eab", "#f4f7ef", ("динамо минск", "минск")),
    Club("Локомотив", "Ярославль", "#ff7a5c", "#e23b2f", "#fff7f4", ("локомотив", "локо", "локомотив ярославль")),
    Club("Металлург", "Магнитогорск", "#b7d4f2", "#1f4e79", "#f4f7ef", ("металлург", "магнитка", "металлург мг", "металлург магнитогорск")),
    Club("Автомобилист", "Екатеринбург", "#ffc14d", "#f5a100", "#1a1204", ("автомобилист", "авто")),
    Club("Трактор", "Челябинск", "#ffc14d", "#f08a00", "#1a1204", ("трактор",)),
    Club("Спартак", "Москва", "#ff6b5c", "#c8102e", "#fff7f4", ("спартак", "спартак москва")),
    Club("Сочи", "Сочи", "#5ee0c2", "#0c7d6b", "#f4f7ef", ("сочи", "хк сочи")),
    Club("Торпедо", "Нижний Новгород", "#ff6b5c", "#d0121a", "#fff7f4", ("торпедо", "торпедо нн")),
    Club("Нефтехимик", "Нижнекамск", "#7ec8ff", "#0a6a9c", "#f4f7ef", ("нефтехимик", "нефтехим")),
    Club("Барыс", "Астана", "#8ecfff", "#0b6e9a", "#f4f7ef", ("барыс",)),
    Club("Адмирал", "Владивосток", "#ffc14d", "#e87700", "#1a1204", ("адмирал",)),
    Club("Амур", "Хабаровск", "#ff6b78", "#c41230", "#fff7f4", ("амур",)),
    Club("Куньлунь Ред Стар", "Пекин", "#ff6b5c", "#c8102e", "#fff7f4", ("куньлунь", "куньлунь ред стар", "ред стар")),
    Club("Драконы", "Шанхай", "#ff6b5c", "#c8102e", "#fff7f4", ("драконы", "шанхай", "драконы шанхай")),
    Club("Витязь", "Московская область", "#d2b0ff", "#5b2a86", "#f7f2ff", ("витязь",)),
    Club("Северсталь", "Череповец", "#ffc14d", "#e0a000", "#1a1204", ("северсталь",)),
    Club("Сибирь", "Новосибирск", "#8eb6ff", "#0a4f9e", "#f4f7ef", ("сибирь",)),
)


def normalize_name(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = text.replace("«", "").replace("»", "").replace('"', "").replace("'", "")
    text = re.sub(r"\bхк\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text


def find_clubs(query: str) -> list[Club]:
    needle = normalize_name(query)
    if not needle:
        return []
    exact = [
        club
        for club in _CLUBS
        if needle == normalize_name(club.name) or needle in club.aliases
    ]
    if exact:
        return exact
    if len(needle) < 3:
        return []
    partial: list[Club] = []
    for club in _CLUBS:
        names = (normalize_name(club.name), *club.aliases)
        if any(name.startswith(needle) or needle.startswith(name) for name in names):
            partial.append(club)
    return partial


def custom_club(name: str, *, side: str) -> Club:
    cleaned = re.sub(r"\s+", " ", name).strip()
    if side == "away":
        return Club(cleaned, "", "#8eb6ee", "#1e4e96", "#f4f7ef")
    return Club(cleaned, "", "#d6ff3c", "#d6ff3c", "#0a1408")


def resolve_club(name: str, *, side: str) -> tuple[Club, list[Club]]:
    hits = find_clubs(name)
    if len(hits) == 1:
        return hits[0], []
    if len(hits) > 1:
        return custom_club(name, side=side), hits
    return custom_club(name, side=side), []
