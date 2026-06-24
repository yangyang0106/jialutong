import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Header, HTTPException


SESSION_DAYS = 30
BIND_CODE_MINUTES = 30


FAMILY_ADMIN = "FAMILY_ADMIN"
FAMILY_MEMBER = "FAMILY_MEMBER"
ELDER_USER = "ELDER_USER"
SUPER_ADMIN = "SUPER_ADMIN"


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()


def _normalize_code(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


class AuthStore:
    def __init__(self, db_path: Path, legacy_token: str) -> None:
        self.db_path = db_path
        self.legacy_token = legacy_token
        self.lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS families (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  username TEXT NOT NULL UNIQUE,
                  wechat_openid TEXT UNIQUE,
                  display_name TEXT NOT NULL,
                  password_salt TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS family_members (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  role TEXT NOT NULL CHECK(role IN ('FAMILY_ADMIN', 'FAMILY_MEMBER', 'GUARDIAN', 'ELDER_USER')),
                  relation TEXT NOT NULL DEFAULT '家属',
                  status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'DISABLED')) DEFAULT 'ACTIVE',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(family_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS elders (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  phone TEXT NOT NULL DEFAULT '',
                  note TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'DISABLED')) DEFAULT 'ACTIVE',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_elder_bindings (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  elder_id TEXT NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
                  relation TEXT NOT NULL DEFAULT '家属',
                  can_manage_routes INTEGER NOT NULL DEFAULT 0,
                  can_receive_help INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  UNIQUE(user_id, elder_id)
                );

                CREATE TABLE IF NOT EXISTS elder_bind_codes (
                  code TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                  elder_id TEXT NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
                  created_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  relation TEXT NOT NULL DEFAULT '本人',
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  used_at TEXT NOT NULL DEFAULT '',
                  used_by_user_id TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS emergency_contacts (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                  elder_id TEXT NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  relation TEXT NOT NULL DEFAULT '',
                  phone TEXT NOT NULL,
                  priority INTEGER NOT NULL DEFAULT 1,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  token_hash TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_family_members_user_id ON family_members(user_id);
                CREATE INDEX IF NOT EXISTS idx_family_members_family_id ON family_members(family_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_elders_family_id ON elders(family_id);
                CREATE INDEX IF NOT EXISTS idx_bindings_family_id ON user_elder_bindings(family_id);
                CREATE INDEX IF NOT EXISTS idx_contacts_elder_id ON emergency_contacts(elder_id);
                """
            )
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
        now = _now_iso()
        for row in rows:
            role = row["role"] if row["role"] in {FAMILY_ADMIN, FAMILY_MEMBER, ELDER_USER} else FAMILY_MEMBER
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

    def has_users(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return bool(row["count"])

    def bootstrap(self, family_name: str, username: str, password: str) -> dict[str, Any]:
        family_name = family_name.strip() or "我的家庭"
        username = username.strip()
        self._validate_username_password(username, password)
        now = _now_iso()
        with self.lock, self._connect() as conn:
            if conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]:
                raise HTTPException(status_code=409, detail="家庭账号已创建，请直接登录")
            family_id = self._create_family(conn, family_name, now)
            user_id = f"user-{secrets.token_hex(8)}"
            salt = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO users (
                  id, username, display_name, password_salt, password_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, username, salt, _hash_password(password, salt), now, now),
            )
            self._ensure_family_member(conn, family_id, user_id, FAMILY_ADMIN, "家属", now)
            elder_id = self._create_default_elder(conn, family_id, now)
            self._ensure_elder_binding(conn, family_id, user_id, elder_id, "家属", 1, 1, now)
            user = self._load_user(conn, user_id)
        return self._public_user(user, family_id)

    def login(self, username: str, password: str) -> dict[str, Any]:
        username = username.strip()
        with self.lock, self._connect() as conn:
            user = self._load_user_by_username(conn, username)
            if not user:
                raise HTTPException(status_code=401, detail="账号或密码不正确")
            expected = _hash_password(password, user["password_salt"])
            if not hmac.compare_digest(expected, user["password_hash"]):
                raise HTTPException(status_code=401, detail="账号或密码不正确")
            family_id = self._primary_family_id(conn, user["id"])
            if not family_id:
                raise HTTPException(status_code=403, detail="账号尚未加入家庭")
            token, expires_at = self._create_session(conn, user["id"], family_id)
        return {"token": token, "user": self._public_user(user, family_id), "expiresAt": expires_at}

    def wechat_login(self, openid: str, family_name: str = "我的家庭") -> dict[str, Any]:
        openid = openid.strip()
        if not openid:
            raise HTTPException(status_code=401, detail="微信登录失败，请重试")
        family_name = family_name.strip() or "我的家庭"
        with self.lock, self._connect() as conn:
            user = self._load_user_by_wechat_openid(conn, openid)
            if not user:
                user = self._create_wechat_user(conn, openid)
            family_id = self._primary_family_id(conn, user["id"])
            if not family_id:
                family_id = self._create_wechat_family_for_user(conn, user["id"], family_name)
            token, expires_at = self._create_session(conn, user["id"], family_id)
        return {"token": token, "user": self._public_user(user, family_id), "expiresAt": expires_at}

    def wechat_bind_elder(self, openid: str, bind_code: str) -> dict[str, Any]:
        openid = openid.strip()
        code = _normalize_code(bind_code)
        if not openid or not code:
            raise HTTPException(status_code=400, detail="绑定信息不完整")
        with self.lock, self._connect() as conn:
            bind = self._load_active_bind_code(conn, code)
            user = self._load_user_by_wechat_openid(conn, openid)
            if not user:
                user = self._create_wechat_user(conn, openid, display_name="老人微信")
            now = _now_iso()
            self._ensure_family_member(conn, bind["family_id"], user["id"], ELDER_USER, bind["relation"] or "本人", now)
            self._ensure_elder_binding(conn, bind["family_id"], user["id"], bind["elder_id"], bind["relation"] or "本人", 0, 0, now)
            conn.execute(
                "UPDATE elder_bind_codes SET used_at = ?, used_by_user_id = ? WHERE code = ?",
                (now, user["id"], code),
            )
            token, expires_at = self._create_session(conn, user["id"], bind["family_id"])
            elder = self._load_elder(conn, bind["elder_id"])
        return {
            "token": token,
            "user": self._public_user(user, bind["family_id"]),
            "elder": self._public_elder(elder),
            "expiresAt": expires_at,
        }

    def logout(self, token: str) -> None:
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (self._hash_token(token),))

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        if self._legacy_token_enabled() and authorization == f"Bearer {self.legacy_token}":
            return {
                "authType": "LEGACY_TOKEN",
                "role": SUPER_ADMIN,
                "familyId": None,
                "userId": "legacy",
                "id": "legacy",
                "accessibleElderIds": [],
            }
        token = self._extract_bearer_token(authorization)
        with self.lock, self._connect() as conn:
            self._delete_expired_sessions(conn)
            session = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?",
                (self._hash_token(token),),
            ).fetchone()
            if not session:
                raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
            user = self._load_user(conn, session["user_id"])
            if not user:
                raise HTTPException(status_code=401, detail="账号不存在，请重新登录")
        return {**self._public_user(user, session["family_id"]), "authType": "SESSION"}

    def require_family_admin(self, principal: dict[str, Any]) -> None:
        self._require_family_admin(principal)

    def me(self, authorization: str | None) -> dict[str, Any]:
        principal = self.authenticate(authorization)
        return {
            "user": principal,
            "elders": self.list_elders(principal),
            "bootstrapped": True,
        }

    def status(self) -> dict[str, bool]:
        return {"bootstrapped": self.has_users()}

    def list_elders(self, principal: dict[str, Any]) -> list[dict[str, Any]]:
        if principal.get("authType") == "LEGACY_TOKEN":
            return []
        family_id = principal.get("familyId")
        if not family_id:
            return []
        with self._connect() as conn:
            if principal.get("role") in {FAMILY_ADMIN, SUPER_ADMIN, "GUARDIAN"}:
                rows = conn.execute(
                    """
                    SELECT e.*, '' AS relation, 1 AS can_manage_routes, 1 AS can_receive_help
                    FROM elders e
                    WHERE e.family_id = ? AND e.status = 'ACTIVE'
                    ORDER BY e.created_at ASC
                    """,
                    (family_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT e.*, b.relation, b.can_manage_routes, b.can_receive_help
                    FROM elders e
                    JOIN user_elder_bindings b ON b.elder_id = e.id
                    WHERE b.user_id = ? AND e.family_id = ? AND e.status = 'ACTIVE'
                    ORDER BY e.created_at ASC
                    """,
                    (principal["id"], family_id),
                ).fetchall()
        return [self._public_elder(row) for row in rows]

    def create_elder(
        self,
        principal: dict[str, Any],
        name: str,
        phone: str = "",
        note: str = "",
        relation: str = "家属",
    ) -> dict[str, Any]:
        self._require_family_admin(principal)
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="老人姓名不能为空")
        now = _now_iso()
        elder_id = f"elder-{secrets.token_hex(8)}"
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO elders (id, family_id, name, phone, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (elder_id, principal["familyId"], name, phone.strip(), note.strip(), now, now),
            )
            self._ensure_elder_binding(
                conn,
                principal["familyId"],
                principal["id"],
                elder_id,
                relation.strip() or "家属",
                1,
                1,
                now,
            )
            elder = self._load_elder(conn, elder_id)
        return self._public_elder(elder)

    def update_elder(
        self,
        principal: dict[str, Any],
        elder_id: str,
        name: str,
        phone: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        self._require_family_admin(principal)
        self._require_elder_access(principal, elder_id)
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="老人姓名不能为空")
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE elders
                SET name = ?, phone = ?, note = ?, updated_at = ?
                WHERE id = ? AND family_id = ?
                """,
                (name, phone.strip(), note.strip(), _now_iso(), elder_id, principal["familyId"]),
            )
            elder = self._load_elder(conn, elder_id)
        return self._public_elder(elder)

    def get_emergency_contact(
        self, principal: dict[str, Any], elder_id: str = ""
    ) -> dict[str, Any]:
        resolved_elder_id = self._resolve_contact_elder_id(principal, elder_id)
        if not resolved_elder_id:
            return self._empty_emergency_contact()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM emergency_contacts
                WHERE family_id = ? AND elder_id = ? AND enabled = 1
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (principal.get("familyId"), resolved_elder_id),
            ).fetchone()
        if not row:
            return self._empty_emergency_contact(resolved_elder_id)
        return self._public_emergency_contact(row)

    def save_emergency_contact(
        self,
        principal: dict[str, Any],
        elder_id: str = "",
        name: str = "",
        relation: str = "",
        phone: str = "",
    ) -> dict[str, Any]:
        self._require_family_admin(principal)
        resolved_elder_id = self._resolve_contact_elder_id(principal, elder_id)
        if not resolved_elder_id:
            raise HTTPException(status_code=400, detail="请先创建老人档案")
        name = name.strip()
        relation = relation.strip()
        phone = phone.strip()
        if not name:
            raise HTTPException(status_code=400, detail="联系人姓名不能为空")
        if not relation:
            raise HTTPException(status_code=400, detail="联系人关系不能为空")
        if not phone:
            raise HTTPException(status_code=400, detail="求助电话不能为空")
        now = _now_iso()
        with self.lock, self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM emergency_contacts
                WHERE family_id = ? AND elder_id = ? AND priority = 1
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (principal["familyId"], resolved_elder_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE emergency_contacts
                    SET name = ?, relation = ?, phone = ?, enabled = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, relation, phone, now, existing["id"]),
                )
                contact_id = existing["id"]
            else:
                contact_id = f"contact-{secrets.token_hex(8)}"
                conn.execute(
                    """
                    INSERT INTO emergency_contacts (
                      id, family_id, elder_id, name, relation, phone, priority, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                    """,
                    (contact_id, principal["familyId"], resolved_elder_id, name, relation, phone, now, now),
                )
            contact = conn.execute(
                "SELECT * FROM emergency_contacts WHERE id = ?",
                (contact_id,),
            ).fetchone()
        return self._public_emergency_contact(contact)

    def create_elder_bind_code(
        self,
        principal: dict[str, Any],
        elder_id: str,
        relation: str = "本人",
    ) -> dict[str, Any]:
        self._require_family_admin(principal)
        self._require_elder_access(principal, elder_id)
        now_dt = _now()
        expires_at = (now_dt + timedelta(minutes=BIND_CODE_MINUTES)).isoformat()
        now = now_dt.isoformat()
        relation = relation.strip() or "本人"
        with self.lock, self._connect() as conn:
            self._load_elder(conn, elder_id)
            for _ in range(5):
                code = _normalize_code(secrets.token_urlsafe(6))[:8]
                if len(code) < 6:
                    continue
                try:
                    conn.execute(
                        """
                        INSERT INTO elder_bind_codes (
                          code, family_id, elder_id, created_by_user_id, relation, created_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (code, principal["familyId"], elder_id, principal["id"], relation, now, expires_at),
                    )
                    return {"code": code, "elderId": elder_id, "relation": relation, "expiresAt": expires_at}
                except sqlite3.IntegrityError:
                    continue
        raise HTTPException(status_code=500, detail="绑定码生成失败，请重试")


    def bind_elder(self, principal: dict[str, Any], code: str) -> dict[str, Any]:
        if principal.get("authType") == "LEGACY_TOKEN":
            raise HTTPException(status_code=403, detail="请使用微信账号绑定老人")
        bind_code = _normalize_code(code)
        if not bind_code:
            raise HTTPException(status_code=400, detail="绑定码不能为空")
        with self.lock, self._connect() as conn:
            bind = self._load_active_bind_code(conn, bind_code)
            user = self._load_user(conn, principal["id"])
            if not user:
                raise HTTPException(status_code=401, detail="账号不存在，请重新登录")
            now = _now_iso()
            self._ensure_family_member(conn, bind["family_id"], user["id"], ELDER_USER, bind["relation"] or "本人", now)
            self._ensure_elder_binding(conn, bind["family_id"], user["id"], bind["elder_id"], bind["relation"] or "本人", 0, 0, now)
            conn.execute(
                "UPDATE elder_bind_codes SET used_at = ?, used_by_user_id = ? WHERE code = ?",
                (now, user["id"], bind_code),
            )
            elder = self._load_elder(conn, bind["elder_id"])
        return {
            "user": self._public_user(user, bind["family_id"]),
            "elder": self._public_elder(elder),
        }

    def _validate_username_password(self, username: str, password: str) -> None:
        if len(username) < 2:
            raise HTTPException(status_code=400, detail="账号至少需要 2 个字符")
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="密码至少需要 6 位")

    def _require_family_admin(self, principal: dict[str, Any]) -> None:
        if principal.get("authType") == "LEGACY_TOKEN":
            return
        if principal.get("role") not in {FAMILY_ADMIN, SUPER_ADMIN}:
            raise HTTPException(status_code=403, detail="只有家庭管理员可以操作")

    def _legacy_token_enabled(self) -> bool:
        token = (self.legacy_token or "").strip()
        return bool(token and token != "change-me")

    def _super_admin_openids(self) -> set[str]:
        raw = os.getenv("JIALUTONG_SUPER_ADMIN_OPENIDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _is_super_admin_user(self, user: sqlite3.Row | dict[str, Any]) -> bool:
        openid = user["wechat_openid"] if "wechat_openid" in user.keys() else ""
        return bool(openid and openid in self._super_admin_openids())

    def _require_elder_access(self, principal: dict[str, Any], elder_id: str) -> None:
        if principal.get("authType") == "LEGACY_TOKEN" or principal.get("role") == SUPER_ADMIN:
            return
        if elder_id not in set(principal.get("accessibleElderIds") or []):
            raise HTTPException(status_code=404, detail="老人档案不存在")

    def _resolve_contact_elder_id(self, principal: dict[str, Any], elder_id: str = "") -> str:
        elder_id = elder_id.strip()
        if elder_id:
            self._require_elder_access(principal, elder_id)
            return elder_id
        accessible_elder_ids = principal.get("accessibleElderIds") or []
        if accessible_elder_ids:
            return accessible_elder_ids[0]
        family_id = principal.get("familyId")
        if not family_id:
            return ""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM elders
                WHERE family_id = ? AND status = 'ACTIVE'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (family_id,),
            ).fetchone()
        return row["id"] if row else ""

    def _create_family(self, conn: sqlite3.Connection, family_name: str, now: str) -> str:
        family_id = f"family-{secrets.token_hex(8)}"
        conn.execute(
            "INSERT INTO families (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (family_id, family_name, now, now),
        )
        return family_id

    def _create_default_elder(self, conn: sqlite3.Connection, family_id: str, now: str) -> str:
        elder_id = f"elder-{secrets.token_hex(8)}"
        conn.execute(
            """
            INSERT INTO elders (id, family_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (elder_id, family_id, "默认老人", now, now),
        )
        return elder_id

    def _create_wechat_user(
        self, conn: sqlite3.Connection, openid: str, display_name: str = "微信用户"
    ) -> sqlite3.Row:
        now = _now_iso()
        user_id = f"user-{secrets.token_hex(8)}"
        username = f"wx_{hashlib.sha256(openid.encode('utf-8')).hexdigest()[:24]}"
        salt = secrets.token_hex(16)
        conn.execute(
            """
            INSERT INTO users (
              id, username, wechat_openid, display_name, password_salt, password_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                openid,
                display_name,
                salt,
                _hash_password(secrets.token_urlsafe(18), salt),
                now,
                now,
            ),
        )
        user = self._load_user(conn, user_id)
        if not user:
            raise HTTPException(status_code=500, detail="创建微信账号失败")
        return user

    def _create_wechat_family_for_user(
        self, conn: sqlite3.Connection, user_id: str, family_name: str
    ) -> str:
        now = _now_iso()
        family_id = self._create_family(conn, family_name, now)
        self._ensure_family_member(conn, family_id, user_id, FAMILY_ADMIN, "家属", now)
        elder_id = self._create_default_elder(conn, family_id, now)
        self._ensure_elder_binding(conn, family_id, user_id, elder_id, "家属", 1, 1, now)
        return family_id

    def _ensure_family_member(
        self,
        conn: sqlite3.Connection,
        family_id: str,
        user_id: str,
        role: str,
        relation: str,
        now: str,
    ) -> None:
        existing = conn.execute(
            "SELECT id, role FROM family_members WHERE family_id = ? AND user_id = ?",
            (family_id, user_id),
        ).fetchone()
        if existing:
            if existing["role"] != FAMILY_ADMIN and role == FAMILY_ADMIN:
                conn.execute(
                    "UPDATE family_members SET role = ?, relation = ?, status = 'ACTIVE', updated_at = ? WHERE id = ?",
                    (role, relation, now, existing["id"]),
                )
            return
        conn.execute(
            """
            INSERT INTO family_members (id, family_id, user_id, role, relation, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"member-{secrets.token_hex(8)}", family_id, user_id, role, relation, now, now),
        )

    def _ensure_elder_binding(
        self,
        conn: sqlite3.Connection,
        family_id: str,
        user_id: str,
        elder_id: str,
        relation: str,
        can_manage_routes: int,
        can_receive_help: int,
        now: str,
    ) -> None:
        existing = conn.execute(
            "SELECT id FROM user_elder_bindings WHERE user_id = ? AND elder_id = ?",
            (user_id, elder_id),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE user_elder_bindings
                SET relation = ?, can_manage_routes = ?, can_receive_help = ?
                WHERE id = ?
                """,
                (relation, can_manage_routes, can_receive_help, existing["id"]),
            )
            return
        conn.execute(
            """
            INSERT INTO user_elder_bindings (
              id, family_id, user_id, elder_id, relation, can_manage_routes, can_receive_help, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"binding-{secrets.token_hex(8)}",
                family_id,
                user_id,
                elder_id,
                relation,
                can_manage_routes,
                can_receive_help,
                now,
            ),
        )

    def _create_session(self, conn: sqlite3.Connection, user_id: str, family_id: str) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        expires_at = (_now() + timedelta(days=SESSION_DAYS)).isoformat()
        self._delete_expired_sessions(conn)
        conn.execute(
            """
            INSERT INTO sessions (token_hash, user_id, family_id, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self._hash_token(token), user_id, family_id, _now_iso(), expires_at),
        )
        return token, expires_at

    def _primary_family_id(self, conn: sqlite3.Connection, user_id: str) -> str:
        row = conn.execute(
            """
            SELECT family_id FROM family_members
            WHERE user_id = ? AND status = 'ACTIVE'
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return row["family_id"] if row else ""

    def _load_active_bind_code(self, conn: sqlite3.Connection, code: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM elder_bind_codes WHERE code = ?", (code,)).fetchone()
        if not row or row["used_at"]:
            raise HTTPException(status_code=404, detail="绑定码不存在或已使用")
        expires_at = _parse_time(row["expires_at"])
        if not expires_at or expires_at <= _now():
            raise HTTPException(status_code=410, detail="绑定码已过期，请让家人重新生成")
        return row

    def _load_user(self, conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def _load_user_by_username(self, conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    def _load_user_by_wechat_openid(
        self, conn: sqlite3.Connection, openid: str
    ) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE wechat_openid = ?", (openid,)).fetchone()

    def _load_elder(self, conn: sqlite3.Connection, elder_id: str) -> sqlite3.Row:
        elder = conn.execute(
            """
            SELECT e.*, b.relation, b.can_manage_routes, b.can_receive_help
            FROM elders e
            LEFT JOIN user_elder_bindings b ON b.elder_id = e.id
            WHERE e.id = ?
            ORDER BY b.created_at ASC
            """,
            (elder_id,),
        ).fetchone()
        if not elder:
            raise HTTPException(status_code=404, detail="老人档案不存在")
        return elder

    def _public_user(self, user: sqlite3.Row | dict[str, Any], family_id: str = "") -> dict[str, Any]:
        user_id = user["id"]
        with self._connect() as conn:
            memberships = conn.execute(
                """
                SELECT m.*, f.name AS family_name
                FROM family_members m
                JOIN families f ON f.id = m.family_id
                WHERE m.user_id = ? AND m.status = 'ACTIVE'
                ORDER BY m.created_at ASC
                """,
                (user_id,),
            ).fetchall()
            if not family_id and memberships:
                family_id = memberships[0]["family_id"]
            membership = next((item for item in memberships if item["family_id"] == family_id), None)
            elder_rows = conn.execute(
                "SELECT elder_id FROM user_elder_bindings WHERE user_id = ? AND family_id = ?",
                (user_id, family_id),
            ).fetchall()
        role = membership["role"] if membership else FAMILY_MEMBER
        if self._is_super_admin_user(user):
            role = SUPER_ADMIN
        accessible_elder_ids = [row["elder_id"] for row in elder_rows]
        return {
            "id": user["id"],
            "familyId": family_id,
            "familyName": membership["family_name"] if membership else "",
            "username": user["username"],
            "wechatBound": bool(user["wechat_openid"]) if "wechat_openid" in user.keys() else False,
            "displayName": user["display_name"],
            "role": role,
            "relation": membership["relation"] if membership else "",
            "memberships": [
                {
                    "familyId": item["family_id"],
                    "familyName": item["family_name"],
                    "role": SUPER_ADMIN if self._is_super_admin_user(user) else item["role"],
                    "relation": item["relation"],
                }
                for item in memberships
            ],
            "accessibleElderIds": accessible_elder_ids,
        }

    def _public_elder(self, elder: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": elder["id"],
            "familyId": elder["family_id"],
            "name": elder["name"],
            "phone": elder["phone"],
            "note": elder["note"],
            "status": elder["status"],
            "relation": elder["relation"] if "relation" in elder.keys() else "",
            "canManageRoutes": bool(elder["can_manage_routes"])
            if "can_manage_routes" in elder.keys()
            else False,
            "canReceiveHelp": bool(elder["can_receive_help"])
            if "can_receive_help" in elder.keys()
            else False,
        }

    def _public_emergency_contact(self, contact: sqlite3.Row | None) -> dict[str, Any]:
        if not contact:
            return self._empty_emergency_contact()
        return {
            "id": contact["id"],
            "familyId": contact["family_id"],
            "elderId": contact["elder_id"],
            "name": contact["name"],
            "relation": contact["relation"],
            "phone": contact["phone"],
            "priority": contact["priority"],
            "enabled": bool(contact["enabled"]),
        }

    def _empty_emergency_contact(self, elder_id: str = "") -> dict[str, Any]:
        return {
            "id": "",
            "familyId": "",
            "elderId": elder_id,
            "name": "",
            "relation": "",
            "phone": "",
            "priority": 1,
            "enabled": False,
        }

    def _delete_expired_sessions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT token_hash, expires_at FROM sessions").fetchall()
        expired = [
            row["token_hash"]
            for row in rows
            if not (expires_at := _parse_time(row["expires_at"])) or expires_at <= _now()
        ]
        if expired:
            conn.executemany("DELETE FROM sessions WHERE token_hash = ?", [(item,) for item in expired])

    def _extract_bearer_token(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="请先登录家路通")
        return authorization.removeprefix("Bearer ").strip()

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_super_admin_principal(principal: dict[str, Any]) -> bool:
    return principal.get("authType") == "LEGACY_TOKEN" or principal.get("role") == SUPER_ADMIN


def family_guard(principal: dict[str, Any], route: dict[str, Any]) -> bool:
    if is_super_admin_principal(principal):
        return True
    family_id = route.get("familyId")
    return bool(family_id and family_id == principal.get("familyId"))


def route_owner_patch(principal: dict[str, Any], route: dict[str, Any] | None = None) -> dict[str, str]:
    if principal.get("authType") == "LEGACY_TOKEN":
        return {}
    patch = {
        "familyId": principal["familyId"],
        "ownerUserId": principal["id"],
        "familyName": principal.get("familyName", "我的家庭"),
    }
    elder_id = (route or {}).get("elderId") or ""
    accessible_elder_ids = principal.get("accessibleElderIds") or []
    if elder_id:
        if principal.get("role") != SUPER_ADMIN and elder_id not in accessible_elder_ids:
            raise HTTPException(status_code=404, detail="老人档案不存在")
        patch["elderId"] = elder_id
    elif accessible_elder_ids:
        patch["elderId"] = accessible_elder_ids[0]
    return patch
