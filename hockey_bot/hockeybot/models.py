from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Club:
    name: str
    city: str
    mark: str
    bar: str
    bar_ink: str
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "city": self.city,
            "mark": self.mark,
            "bar": self.bar,
            "bar_ink": self.bar_ink,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Club:
        return cls(
            name=data.get("name", ""),
            city=data.get("city", ""),
            mark=data.get("mark", "#d6ff3c"),
            bar=data.get("bar", "#d6ff3c"),
            bar_ink=data.get("bar_ink", "#0a1408"),
        )


@dataclass
class Goal:
    time: str
    scorer: str
    assists: str = ""
    tag: str = ""


@dataclass
class Footer:
    left: str = ""
    center: str = ""
    right: str = ""
    left_sub: str = ""
    center_sub: str = ""
    right_sub: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "left": self.left,
            "center": self.center,
            "right": self.right,
            "left_sub": self.left_sub,
            "center_sub": self.center_sub,
            "right_sub": self.right_sub,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str] | None) -> Footer:
        data = data or {}
        return cls(
            left=data.get("left", ""),
            center=data.get("center", ""),
            right=data.get("right", ""),
            left_sub=data.get("left_sub", ""),
            center_sub=data.get("center_sub", ""),
            right_sub=data.get("right_sub", ""),
        )


@dataclass
class MatchCard:
    home: Club
    away: Club
    home_score: int | None = None
    away_score: int | None = None
    date: str = ""
    arena: str = ""
    periods: list[str] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    footer: Footer = field(default_factory=Footer)
    note: str = ""
    photo_path: str | None = None
    tournament: str = "КХЛ · 26/27"
    kind: str = "result"

    def to_dict(self) -> dict:
        return {
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "home_score": self.home_score,
            "away_score": self.away_score,
            "date": self.date,
            "arena": self.arena,
            "periods": list(self.periods),
            "goals": [
                {
                    "time": goal.time,
                    "scorer": goal.scorer,
                    "assists": goal.assists,
                    "tag": goal.tag,
                }
                for goal in self.goals
            ],
            "footer": self.footer.to_dict(),
            "note": self.note,
            "photo_path": self.photo_path,
            "tournament": self.tournament,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MatchCard:
        return cls(
            home=Club.from_dict(data["home"]),
            away=Club.from_dict(data["away"]),
            home_score=data.get("home_score"),
            away_score=data.get("away_score"),
            date=data.get("date", ""),
            arena=data.get("arena", ""),
            periods=list(data.get("periods") or []),
            goals=[Goal(**goal) for goal in data.get("goals") or []],
            footer=Footer.from_dict(data.get("footer")),
            note=data.get("note", ""),
            photo_path=data.get("photo_path"),
            tournament=data.get("tournament") or "КХЛ · 26/27",
            kind=data.get("kind") or "result",
        )
