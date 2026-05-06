from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Registration:
    alias: str
    user_id: int
    username: str | None
    first_name: str | None
    updated_at: str


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS registrations (
                    alias TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    code TEXT NOT NULL,
                    company TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    invite_link TEXT,
                    private_note TEXT,
                    created_by_user_id INTEGER NOT NULL,
                    created_by_name TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    actor_user_id INTEGER NOT NULL,
                    actor_name TEXT,
                    action TEXT NOT NULL,
                    payload_json TEXT
                );
                """
            )
            self._apply_migrations(conn)

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        # Backfill private_note column for existing databases.
        row = conn.execute(
            "SELECT 1 FROM pragma_table_info('groups') WHERE name = 'private_note'"
        ).fetchone()
        if not row:
            conn.execute("ALTER TABLE groups ADD COLUMN private_note TEXT")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_registration(
        self, alias: str, user_id: int, username: str | None, first_name: str | None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO registrations(alias, user_id, username, first_name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(alias) DO UPDATE SET
                    user_id=excluded.user_id,
                    username=excluded.username,
                    first_name=excluded.first_name,
                    updated_at=excluded.updated_at
                """,
                (alias.lower().strip(), user_id, username, first_name, self._now_iso()),
            )

    def get_registration(self, alias: str) -> Registration | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT alias, user_id, username, first_name, updated_at FROM registrations WHERE alias = ?",
                (alias.lower().strip(),),
            ).fetchone()

        if not row:
            return None
        return Registration(
            alias=row["alias"],
            user_id=row["user_id"],
            username=row["username"],
            first_name=row["first_name"],
            updated_at=row["updated_at"],
        )

    def get_many_registrations(self, aliases: list[str]) -> dict[str, Registration]:
        clean_aliases = [a.lower().strip() for a in aliases]
        if not clean_aliases:
            return {}
        placeholders = ",".join(["?"] * len(clean_aliases))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT alias, user_id, username, first_name, updated_at FROM registrations WHERE alias IN ({placeholders})",
                clean_aliases,
            ).fetchall()
        return {
            row["alias"]: Registration(
                alias=row["alias"],
                user_id=row["user_id"],
                username=row["username"],
                first_name=row["first_name"],
                updated_at=row["updated_at"],
            )
            for row in rows
        }

    def record_group(
        self,
        chat_id: int,
        code: str,
        company: str,
        group_name: str,
        invite_link: str | None,
        private_note: str | None,
        created_by_user_id: int,
        created_by_name: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO groups(chat_id, code, company, group_name, invite_link, private_note, created_by_user_id, created_by_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    code=excluded.code,
                    company=excluded.company,
                    group_name=excluded.group_name,
                    invite_link=excluded.invite_link,
                    private_note=excluded.private_note,
                    created_by_user_id=excluded.created_by_user_id,
                    created_by_name=excluded.created_by_name,
                    created_at=excluded.created_at
                """,
                (
                    chat_id,
                    code.upper(),
                    company,
                    group_name,
                    invite_link,
                    private_note,
                    created_by_user_id,
                    created_by_name,
                    self._now_iso(),
                ),
            )

    def get_group_code(self, chat_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT code FROM groups WHERE chat_id = ?", (chat_id,)).fetchone()
        return row["code"] if row else None

    def get_group(self, chat_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT chat_id, code, company, group_name, invite_link, private_note, created_by_name, created_at
                FROM groups
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        return row

    def find_group(self, code: str, company: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT chat_id, code, company, group_name, invite_link, created_at
                FROM groups
                WHERE code = ? AND lower(company) = lower(?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (code.upper(), company.strip()),
            ).fetchone()
        return row

    def append_audit(
        self, actor_user_id: int, actor_name: str | None, action: str, payload_json: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log(created_at, actor_user_id, actor_name, action, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._now_iso(), actor_user_id, actor_name, action, payload_json),
            )

    def count_registrations(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM registrations").fetchone()
        return int(row["count"]) if row else 0

    def count_groups(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM groups").fetchone()
        return int(row["count"]) if row else 0

    def list_recent_groups(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, code, company, group_name, invite_link, private_note, created_by_name, created_at
                FROM groups
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return list(rows)

    def list_recent_audit(self, limit: int = 30) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, actor_user_id, actor_name, action, payload_json
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return list(rows)
