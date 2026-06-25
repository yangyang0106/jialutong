import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.auth_schema import AUTH_SCHEMA_SQL


class SqliteAuthRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(AUTH_SCHEMA_SQL)
            # Old local DBs may still have columns from the temporary MVP account model.
            self._ensure_column(conn, "users", "wechat_openid", "TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_openid ON users(wechat_openid)"
            )
            self._migrate_old_user_roles(conn)

    def _ensure_column(
        self, conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _migrate_old_user_roles(self, conn: sqlite3.Connection) -> None:
        columns = self._table_columns(conn, "users")
        if not {"family_id", "role"}.issubset(columns):
            return
        rows = conn.execute(
            "SELECT id, family_id, role FROM users WHERE family_id IS NOT NULL AND family_id != ''"
        ).fetchall()
        now = datetime.now(UTC).isoformat()
        for row in rows:
            role = row["role"] if row["role"] in {"FAMILY_ADMIN", "FAMILY_MEMBER", "ELDER_USER"} else "FAMILY_MEMBER"
            exists = conn.execute(
                "SELECT id FROM family_members WHERE family_id = ? AND user_id = ?",
                (row["family_id"], row["id"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO family_members (id, family_id, user_id, role, relation, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"member-{secrets.token_hex(8)}", row["family_id"], row["id"], role, "家属", now, now),
            )
