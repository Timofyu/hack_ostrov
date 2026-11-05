from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hockeybot.templates_lib import PostTemplate


@dataclass
class Settings:
    default_template: str = "builtin:result"
    channel_id: str | None = None
    channel_title: str | None = None
    tournament: str = "КХЛ · 26/27"


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_settings (
                    owner_id INTEGER PRIMARY KEY,
                    default_template TEXT NOT NULL DEFAULT 'builtin:result',
                    channel_id TEXT,
                    channel_title TEXT,
                    tournament TEXT NOT NULL DEFAULT 'КХЛ · 26/27'
                );
                """
            )

    def settings(self, owner_id: int) -> Settings:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT default_template, channel_id, channel_title, tournament FROM user_settings WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()
        if row is None:
            return Settings()
        return Settings(
            default_template=row["default_template"] or "builtin:result",
            channel_id=row["channel_id"],
            channel_title=row["channel_title"],
            tournament=row["tournament"] or "КХЛ · 26/27",
        )

    def set_default_template(self, owner_id: int, template_id: str) -> None:
        self._ensure_settings(owner_id)
        with self._conn() as conn:
            conn.execute(
                "UPDATE user_settings SET default_template = ? WHERE owner_id = ?",
                (template_id, owner_id),
            )

    def set_channel(self, owner_id: int, channel_id: str, title: str) -> None:
        self._ensure_settings(owner_id)
        with self._conn() as conn:
            conn.execute(
                "UPDATE user_settings SET channel_id = ?, channel_title = ? WHERE owner_id = ?",
                (channel_id, title, owner_id),
            )

    def clear_channel(self, owner_id: int) -> None:
        self._ensure_settings(owner_id)
        with self._conn() as conn:
            conn.execute(
                "UPDATE user_settings SET channel_id = NULL, channel_title = NULL WHERE owner_id = ?",
                (owner_id,),
            )

    def set_tournament(self, owner_id: int, tournament: str) -> None:
        self._ensure_settings(owner_id)
        with self._conn() as conn:
            conn.execute(
                "UPDATE user_settings SET tournament = ? WHERE owner_id = ?",
                (tournament, owner_id),
            )

    def list_templates(self, owner_id: int) -> list[PostTemplate]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, kind, body FROM user_templates WHERE owner_id = ? ORDER BY id",
                (owner_id,),
            ).fetchall()
        return [
            PostTemplate(
                id=f"user:{row['id']}",
                name=row["name"],
                kind=row["kind"],
                body=row["body"],
            )
            for row in rows
        ]

    def add_template(self, owner_id: int, name: str, kind: str, body: str) -> PostTemplate:
        created = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO user_templates (owner_id, name, kind, body, created_at) VALUES (?, ?, ?, ?, ?)",
                (owner_id, name, kind, body, created),
            )
            template_id = int(cursor.lastrowid)
        return PostTemplate(id=f"user:{template_id}", name=name, kind=kind, body=body)

    def get_template(self, owner_id: int, template_id: str) -> PostTemplate | None:
        raw_id = _user_id(template_id)
        if raw_id is None:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name, kind, body FROM user_templates WHERE id = ? AND owner_id = ?",
                (raw_id, owner_id),
            ).fetchone()
        if row is None:
            return None
        return PostTemplate(id=f"user:{row['id']}", name=row["name"], kind=row["kind"], body=row["body"])

    def update_body(self, owner_id: int, template_id: str, body: str) -> bool:
        raw_id = _user_id(template_id)
        if raw_id is None:
            return False
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE user_templates SET body = ? WHERE id = ? AND owner_id = ?",
                (body, raw_id, owner_id),
            )
        return cursor.rowcount > 0

    def delete_template(self, owner_id: int, template_id: str) -> bool:
        raw_id = _user_id(template_id)
        if raw_id is None:
            return False
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_templates WHERE id = ? AND owner_id = ?",
                (raw_id, owner_id),
            )
        return cursor.rowcount > 0

    def _ensure_settings(self, owner_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_settings (owner_id) VALUES (?)",
                (owner_id,),
            )

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _user_id(template_id: str) -> int | None:
    if not template_id.startswith("user:"):
        return None
    raw = template_id.split(":", 1)[1]
    if not raw.isdigit():
        return None
    return int(raw)
