from __future__ import annotations

import re
from collections import Counter

from hockeybot.models import Footer, Goal, MatchCard


def build_context(card: MatchCard) -> dict[str, str]:
    score = ""
    if card.home_score is not None and card.away_score is not None:
        score = f"{card.home_score}:{card.away_score}"
    when = " · ".join(part for part in (card.date, card.arena) if part)
    periods_line = ""
    if card.periods:
        periods_line = "Периоды: " + ", ".join(card.periods)
    return {
        "home": card.home.name,
        "away": card.away.name,
        "home_city": card.home.city,
        "away_city": card.away.city,
        "score": score,
        "home_score": "" if card.home_score is None else str(card.home_score),
        "away_score": "" if card.away_score is None else str(card.away_score),
        "date": card.date,
        "arena": card.arena,
        "when": when,
        "periods_line": periods_line,
        "goals_block": goals_block(card.goals),
        "scorers": scorers_line(card.goals),
        "note": card.note.strip(),
        "goalie_line": goalie_line(card.footer),
        "tournament": card.tournament,
        "url": "",
    }


def render_caption(body: str, ctx: dict[str, str]) -> str:
    rendered: list[str] = []
    for line in body.splitlines():
        keys = re.findall(r"\{([a-z_]+)\}", line)
        known = [key for key in keys if key in ctx]
        if known and all(not ctx[key].strip() for key in known):
            continue
        rendered.append(_substitute(line, ctx).rstrip())
    return _collapse(rendered)


def goals_block(goals: list[Goal]) -> str:
    lines: list[str] = []
    for goal in goals:
        piece = f"{goal.time} {goal.scorer}"
        if goal.assists:
            piece += f" ({goal.assists})"
        if goal.tag:
            piece += f", {goal.tag}."
        lines.append(piece)
    return "\n".join(lines)


def scorers_line(goals: list[Goal]) -> str:
    counts = Counter(goal.scorer for goal in goals)
    order: list[str] = []
    for goal in goals:
        if goal.scorer not in order:
            order.append(goal.scorer)
    bits = []
    for name in order:
        count = counts[name]
        bits.append(f"{name} ×{count}" if count > 1 else name)
    return ", ".join(bits)


def goalie_line(footer: Footer) -> str:
    parts = [footer.left, footer.center, footer.right]
    parts = [part for part in parts if part]
    return " · ".join(parts)


def split_caption(text: str, limit: int = 1024) -> tuple[str, str]:
    if len(text) <= limit:
        return text, ""
    cut = text.rfind("\n", 0, limit)
    if cut < 200:
        cut = limit
    return text[:cut].rstrip(), text[cut:].lstrip()


def _substitute(line: str, ctx: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in ctx:
            return ctx[key]
        return match.group(0)

    return re.sub(r"\{([a-z_]+)\}", replace, line)


def _collapse(lines: list[str]) -> str:
    output: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if output and not blank:
                output.append("")
            blank = True
            continue
        blank = False
        output.append(line)
    return "\n".join(output).strip()
