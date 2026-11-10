from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hockeybot.templates_lib import PostTemplate


@dataclass
class Watch:
    id: int
    owner_id: int
    chat_id: int
    query: str
    created_at: str
    status: str


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
                CREATE TABLE IF NOT EXISTS match_watches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS table_snapshots (
                    season TEXT NOT NULL,
                    day TEXT NOT NULL,
                    conference TEXT NOT NULL,
                    club TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    points INTEGER NOT NULL
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

    def save_result_template(self, owner_id: int, body: str) -> PostTemplate:
        settings = self.settings(owner_id)
        current = self.get_template(owner_id, settings.default_template)
        if current is not None and current.kind == "result":
            self.update_body(owner_id, current.id, body)
            updated = self.get_template(owner_id, current.id)
            return updated or current
        created = self.add_template(owner_id, "Итоги матча", "result", body)
        self.set_default_template(owner_id, created.id)
        return created

    def add_watch(self, owner_id: int, chat_id: int, query: str) -> tuple[Watch, bool]:
        query = " ".join(query.split())
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, owner_id, chat_id, query, created_at, status
                FROM match_watches
                WHERE owner_id = ? AND query = ? AND status = 'pending'
                """,
                (owner_id, query),
            ).fetchone()
            if row is not None:
                return _watch(row), False
            created = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """
                INSERT INTO match_watches (owner_id, chat_id, query, created_at, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (owner_id, chat_id, query, created),
            )
            watch_id = int(cursor.lastrowid)
        return Watch(watch_id, owner_id, chat_id, query, created, "pending"), True

    def pending_watches(self) -> list[Watch]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, owner_id, chat_id, query, created_at, status
                FROM match_watches
                WHERE status = 'pending'
                ORDER BY id
                """
            ).fetchall()
        return [_watch(row) for row in rows]

    def finish_query(self, owner_id: int, query: str, status: str = "done") -> None:
        query = " ".join(query.split())
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE match_watches
                SET status = ?
                WHERE owner_id = ? AND query = ? AND status = 'pending'
                """,
                (status, owner_id, query),
            )

    def finish_watch(self, watch_id: int, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE match_watches SET status = ? WHERE id = ? AND status = 'pending'",
                (status, watch_id),
            )

    def save_table_snapshot(self, season: str, day: str, rows: list[tuple[str, str, int, int]]) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM table_snapshots WHERE season = ? AND day = ?", (season, day))
            conn.executemany(
                """
                INSERT INTO table_snapshots (season, day, conference, club, rank, points)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(season, day, conference, club, rank, points) for conference, club, rank, points in rows],
            )

    def previous_table(self, season: str, before_day: str) -> dict[tuple[str, str], tuple[int, int]]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT day FROM table_snapshots
                WHERE season = ? AND day < ?
                ORDER BY day DESC
                LIMIT 1
                """,
                (season, before_day),
            ).fetchone()
            if row is None:
                return {}
            found = conn.execute(
                """
                SELECT conference, club, rank, points
                FROM table_snapshots
                WHERE season = ? AND day = ?
                """,
                (season, row["day"]),
            ).fetchall()
        return {(item["conference"], item["club"]): (int(item["rank"]), int(item["points"])) for item in found}

    def stop_watches(self, owner_id: int) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE match_watches SET status = 'stopped' WHERE owner_id = ? AND status = 'pending'",
                (owner_id,),
            )
        return cursor.rowcount

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


def _watch(row: sqlite3.Row) -> Watch:
    return Watch(
        id=int(row["id"]),
        owner_id=int(row["owner_id"]),
        chat_id=int(row["chat_id"]),
        query=row["query"],
        created_at=row["created_at"],
        status=row["status"],
    )


def _user_id(template_id: str) -> int | None:
    if not template_id.startswith("user:"):
        return None
    raw = template_id.split(":", 1)[1]
    if not raw.isdigit():
        return None
    return int(raw)
