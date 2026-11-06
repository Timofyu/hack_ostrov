from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    token: str
    db_path: Path
    allowed_user_ids: frozenset[int]
    chrome_path: str | None


def _env_text(name: str) -> str:
    return os.environ.get(name, "").strip().strip('"')


def _env_path(name: str, default: Path) -> Path:
    raw = _env_text(name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    load_dotenv()
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("В hockey_bot/.env нет BOT_TOKEN.")
    allowed: set[int] = set()
    for part in os.environ.get("ALLOWED_USER_IDS", "").split(","):
        part = part.strip()
        if part.isdigit():
            allowed.add(int(part))
    db_path = _env_path("DB_PATH", ROOT / "data" / "bot.sqlite")
    chrome = _env_text("BROWSER_PATH") or _env_text("CHROME_PATH") or None
    return Config(
        token=token,
        db_path=db_path,
        allowed_user_ids=frozenset(allowed),
        chrome_path=chrome,
    )
