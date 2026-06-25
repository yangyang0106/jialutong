import hashlib
import secrets
import sqlite3
from datetime import timedelta
from typing import Any

from fastapi import HTTPException

from app.auth_common import (
    BIND_CODE_MINUTES,
    ELDER_USER,
    FAMILY_ADMIN,
    FAMILY_MEMBER,
    SESSION_DAYS,
    SUPER_ADMIN,
    hash_password,
    normalize_code,
    now,
    now_iso,
    parse_time,
)


class FamilyMembershipService:
    def __init__(self, store) -> None:
        self.store = store

    def require_family_admin(self, principal: dict[str, Any]) -> None:
        if principal.get("role") not in {FAMILY_ADMIN, SUPER_ADMIN}:
            raise HTTPException(status_code=403, detail="只有家庭管理员可以操作")

    def is_super_admin_user(self, user: sqlite3.Row | dict[str, Any]) -> bool:
        openid = user["wechat_openid"] if "wechat_openid" in user.keys() else ""
        return bool(openid and openid in self.super_admin_openids())

    def super_admin_openids(self) -> set[str]:
        return {
            item.strip()
            for item in self.store.super_admin_openids_raw.split(",")
            if item.strip()
        }

    def require_elder_access(self, principal: dict[str, Any], elder_id: str) -> None:
        if principal.get("role") == SUPER_ADMIN:
            return
        if elder_id not in set(principal.get("accessibleElderIds") or []):
            raise HTTPException(status_code=404, detail="老人档案不存在")

    def resolve_contact_elder_id(self, principal: dict[str, Any], elder_id: str = "") -> str:
        elder_id = elder_id.strip()
        if elder_id:
            self.require_elder_access(principal, elder_id)
            return elder_id
        accessible_elder_ids = principal.get("accessibleElderIds") or []
        if accessible_elder_ids:
            return accessible_elder_ids[0]
        family_id = principal.get("familyId")
        if not family_id:
            return ""
        with self.store.connect() as conn:
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

    def create_family(self, conn: sqlite3.Connection, family_name: str, created_at: str) -> str:
        family_id = f"family-{secrets.token_hex(8)}"
        conn.execute(
            "INSERT INTO families (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (family_id, family_name, created_at, created_at),
        )
        return family_id

    def create_default_elder(self, conn: sqlite3.Connection, family_id: str, created_at: str) -> str:
        elder_id = f"elder-{secrets.token_hex(8)}"
        conn.execute(
            """
            INSERT INTO elders (id, family_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (elder_id, family_id, "默认老人", created_at, created_at),
        )
        return elder_id

    def create_wechat_family_for_user(
        self, conn: sqlite3.Connection, user_id: str, family_name: str
    ) -> str:
        created_at = now_iso()
        family_id = self.create_family(conn, family_name, created_at)
        self.ensure_family_member(conn, family_id, user_id, FAMILY_ADMIN, "家属", created_at)
        elder_id = self.create_default_elder(conn, family_id, created_at)
        self.ensure_elder_binding(conn, family_id, user_id, elder_id, "家属", 1, 1, created_at)
        return family_id

    def ensure_family_member(
        self,
        conn: sqlite3.Connection,
        family_id: str,
        user_id: str,
        role: str,
        relation: str,
        updated_at: str,
    ) -> None:
        existing = conn.execute(
            "SELECT id, role FROM family_members WHERE family_id = ? AND user_id = ?",
            (family_id, user_id),
        ).fetchone()
        if existing:
            if existing["role"] != FAMILY_ADMIN and role == FAMILY_ADMIN:
                conn.execute(
                    "UPDATE family_members SET role = ?, relation = ?, status = 'ACTIVE', updated_at = ? WHERE id = ?",
                    (role, relation, updated_at, existing["id"]),
                )
            return
        conn.execute(
            """
            INSERT INTO family_members (id, family_id, user_id, role, relation, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"member-{secrets.token_hex(8)}", family_id, user_id, role, relation, updated_at, updated_at),
        )

    def ensure_elder_binding(
        self,
        conn: sqlite3.Connection,
        family_id: str,
        user_id: str,
        elder_id: str,
        relation: str,
        can_manage_routes: int,
        can_receive_help: int,
        created_at: str,
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
                created_at,
            ),
        )

    def primary_family_id(self, conn: sqlite3.Connection, user_id: str) -> str:
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

    def has_active_family_membership(
        self, conn: sqlite3.Connection, user_id: str, family_id: str
    ) -> bool:
        row = conn.execute(
            """
            SELECT id FROM family_members
            WHERE user_id = ? AND family_id = ? AND status = 'ACTIVE'
            LIMIT 1
            """,
            (user_id, family_id),
        ).fetchone()
        return bool(row)

    def public_user(self, user: sqlite3.Row | dict[str, Any], family_id: str = "") -> dict[str, Any]:
        user_id = user["id"]
        with self.store.connect() as conn:
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
            if membership and membership["role"] in {FAMILY_ADMIN, "GUARDIAN"}:
                elder_rows = conn.execute(
                    "SELECT id AS elder_id FROM elders WHERE family_id = ? AND status = 'ACTIVE'",
                    (family_id,),
                ).fetchall()
            else:
                elder_rows = conn.execute(
                    "SELECT elder_id FROM user_elder_bindings WHERE user_id = ? AND family_id = ?",
                    (user_id, family_id),
                ).fetchall()
        role = membership["role"] if membership else FAMILY_MEMBER
        if self.is_super_admin_user(user):
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
                    "role": SUPER_ADMIN if self.is_super_admin_user(user) else item["role"],
                    "relation": item["relation"],
                }
                for item in memberships
            ],
            "accessibleElderIds": accessible_elder_ids,
        }

    def public_elder(self, elder: sqlite3.Row) -> dict[str, Any]:
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

    def public_emergency_contact(self, contact: sqlite3.Row | None) -> dict[str, Any]:
        if not contact:
            return self.empty_emergency_contact()
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

    def empty_emergency_contact(self, elder_id: str = "") -> dict[str, Any]:
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


class SessionService:
    def __init__(self, store) -> None:
        self.store = store

    def create_session(self, conn: sqlite3.Connection, user_id: str, family_id: str) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        expires_at = (now() + timedelta(days=SESSION_DAYS)).isoformat()
        self.delete_expired_sessions(conn)
        conn.execute(
            """
            INSERT INTO sessions (token_hash, user_id, family_id, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.hash_token(token), user_id, family_id, now_iso(), expires_at),
        )
        return token, expires_at

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        token = self.extract_bearer_token(authorization)
        with self.store.lock, self.store.connect() as conn:
            self.delete_expired_sessions(conn)
            session = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?",
                (self.hash_token(token),),
            ).fetchone()
            if not session:
                raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
            user = self.store.load_user(conn, session["user_id"])
            if not user:
                raise HTTPException(status_code=401, detail="账号不存在，请重新登录")
            if not self.store.memberships.has_active_family_membership(conn, user["id"], session["family_id"]):
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (session["token_hash"],))
                raise HTTPException(status_code=403, detail="家庭成员关系已失效，请重新登录")
        return {**self.store.memberships.public_user(user, session["family_id"]), "authType": "SESSION"}

    def logout(self, token: str) -> None:
        with self.store.lock, self.store.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (self.hash_token(token),))

    def delete_expired_sessions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT token_hash, expires_at FROM sessions").fetchall()
        expired = [
            row["token_hash"]
            for row in rows
            if not (expires_at := parse_time(row["expires_at"])) or expires_at <= now()
        ]
        if expired:
            conn.executemany("DELETE FROM sessions WHERE token_hash = ?", [(item,) for item in expired])

    def extract_bearer_token(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="请先登录家路通")
        return authorization.removeprefix("Bearer ").strip()

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class WechatAuthService:
    def __init__(self, store) -> None:
        self.store = store

    def wechat_login(self, openid: str, family_name: str = "我的家庭") -> dict[str, Any]:
        openid = openid.strip()
        if not openid:
            raise HTTPException(status_code=401, detail="微信登录失败，请重试")
        family_name = family_name.strip() or "我的家庭"
        with self.store.lock, self.store.connect() as conn:
            user = self.store.load_user_by_wechat_openid(conn, openid)
            if not user:
                user = self.create_wechat_user(conn, openid)
                family_id = self.store.memberships.create_wechat_family_for_user(
                    conn, user["id"], family_name
                )
            else:
                family_id = self.store.memberships.primary_family_id(conn, user["id"])
                if not family_id:
                    raise HTTPException(
                        status_code=403,
                        detail="该微信已注册但尚未绑定家庭，请使用老人绑定流程",
                    )
            token, expires_at = self.store.sessions.create_session(conn, user["id"], family_id)
        return {
            "token": token,
            "user": self.store.memberships.public_user(user, family_id),
            "expiresAt": expires_at,
        }

    def create_wechat_user(
        self, conn: sqlite3.Connection, openid: str, display_name: str = "微信用户"
    ) -> sqlite3.Row:
        created_at = now_iso()
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
                hash_password(secrets.token_urlsafe(18), salt),
                created_at,
                created_at,
            ),
        )
        user = self.store.load_user(conn, user_id)
        if not user:
            raise HTTPException(status_code=500, detail="创建微信账号失败")
        return user


class ElderProfileService:
    def __init__(self, store) -> None:
        self.store = store

    def list_elders(self, principal: dict[str, Any]) -> list[dict[str, Any]]:
        family_id = principal.get("familyId")
        if not family_id:
            return []
        with self.store.connect() as conn:
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
        return [self.store.memberships.public_elder(row) for row in rows]

    def create_elder(
        self,
        principal: dict[str, Any],
        name: str,
        phone: str = "",
        note: str = "",
        relation: str = "家属",
    ) -> dict[str, Any]:
        self.store.memberships.require_family_admin(principal)
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="老人姓名不能为空")
        created_at = now_iso()
        elder_id = f"elder-{secrets.token_hex(8)}"
        with self.store.lock, self.store.connect() as conn:
            conn.execute(
                """
                INSERT INTO elders (id, family_id, name, phone, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (elder_id, principal["familyId"], name, phone.strip(), note.strip(), created_at, created_at),
            )
            self.store.memberships.ensure_elder_binding(
                conn,
                principal["familyId"],
                principal["id"],
                elder_id,
                relation.strip() or "家属",
                1,
                1,
                created_at,
            )
            elder = self.store.load_elder(conn, elder_id)
        return self.store.memberships.public_elder(elder)

    def update_elder(
        self,
        principal: dict[str, Any],
        elder_id: str,
        name: str,
        phone: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        self.store.memberships.require_family_admin(principal)
        self.store.memberships.require_elder_access(principal, elder_id)
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="老人姓名不能为空")
        with self.store.lock, self.store.connect() as conn:
            conn.execute(
                """
                UPDATE elders
                SET name = ?, phone = ?, note = ?, updated_at = ?
                WHERE id = ? AND family_id = ?
                """,
                (name, phone.strip(), note.strip(), now_iso(), elder_id, principal["familyId"]),
            )
            elder = self.store.load_elder(conn, elder_id)
        return self.store.memberships.public_elder(elder)


class ElderBindingService:
    def __init__(self, store) -> None:
        self.store = store

    def create_elder_bind_code(
        self,
        principal: dict[str, Any],
        elder_id: str,
        relation: str = "本人",
    ) -> dict[str, Any]:
        self.store.memberships.require_family_admin(principal)
        self.store.memberships.require_elder_access(principal, elder_id)
        now_dt = now()
        expires_at = (now_dt + timedelta(minutes=BIND_CODE_MINUTES)).isoformat()
        created_at = now_dt.isoformat()
        relation = relation.strip() or "本人"
        with self.store.lock, self.store.connect() as conn:
            self.store.load_elder(conn, elder_id)
            for _ in range(5):
                code = normalize_code(secrets.token_urlsafe(6))[:8]
                if len(code) < 6:
                    continue
                try:
                    conn.execute(
                        """
                        INSERT INTO elder_bind_codes (
                          code, family_id, elder_id, created_by_user_id, relation, created_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (code, principal["familyId"], elder_id, principal["id"], relation, created_at, expires_at),
                    )
                    return {"code": code, "elderId": elder_id, "relation": relation, "expiresAt": expires_at}
                except sqlite3.IntegrityError:
                    continue
        raise HTTPException(status_code=500, detail="绑定码生成失败，请重试")

    def bind_elder(self, principal: dict[str, Any], code: str) -> dict[str, Any]:
        bind_code = normalize_code(code)
        if not bind_code:
            raise HTTPException(status_code=400, detail="绑定码不能为空")
        with self.store.lock, self.store.connect() as conn:
            bind = self.store.load_active_bind_code(conn, bind_code)
            if principal.get("familyId") != bind["family_id"]:
                raise HTTPException(status_code=403, detail="绑定码不属于当前家庭")
            user = self.store.load_user(conn, principal["id"])
            if not user:
                raise HTTPException(status_code=401, detail="账号不存在，请重新登录")
            updated_at = now_iso()
            self.store.memberships.ensure_family_member(conn, bind["family_id"], user["id"], ELDER_USER, bind["relation"] or "本人", updated_at)
            self.store.memberships.ensure_elder_binding(conn, bind["family_id"], user["id"], bind["elder_id"], bind["relation"] or "本人", 0, 0, updated_at)
            conn.execute(
                "UPDATE elder_bind_codes SET used_at = ?, used_by_user_id = ? WHERE code = ?",
                (updated_at, user["id"], bind_code),
            )
            elder = self.store.load_elder(conn, bind["elder_id"])
        return {
            "user": self.store.memberships.public_user(user, bind["family_id"]),
            "elder": self.store.memberships.public_elder(elder),
        }

    def wechat_bind_elder(self, openid: str, bind_code: str) -> dict[str, Any]:
        openid = openid.strip()
        code = normalize_code(bind_code)
        if not openid or not code:
            raise HTTPException(status_code=400, detail="绑定信息不完整")
        with self.store.lock, self.store.connect() as conn:
            bind = self.store.load_active_bind_code(conn, code)
            user = self.store.load_user_by_wechat_openid(conn, openid)
            if not user:
                user = self.store.wechat_auth.create_wechat_user(conn, openid, display_name="老人微信")
            updated_at = now_iso()
            self.store.memberships.ensure_family_member(conn, bind["family_id"], user["id"], ELDER_USER, bind["relation"] or "本人", updated_at)
            self.store.memberships.ensure_elder_binding(conn, bind["family_id"], user["id"], bind["elder_id"], bind["relation"] or "本人", 0, 0, updated_at)
            conn.execute(
                "UPDATE elder_bind_codes SET used_at = ?, used_by_user_id = ? WHERE code = ?",
                (updated_at, user["id"], code),
            )
            token, expires_at = self.store.sessions.create_session(conn, user["id"], bind["family_id"])
            elder = self.store.load_elder(conn, bind["elder_id"])
        return {
            "token": token,
            "user": self.store.memberships.public_user(user, bind["family_id"]),
            "elder": self.store.memberships.public_elder(elder),
            "expiresAt": expires_at,
        }


class EmergencyContactService:
    def __init__(self, store) -> None:
        self.store = store

    def get_emergency_contact(
        self, principal: dict[str, Any], elder_id: str = ""
    ) -> dict[str, Any]:
        resolved_elder_id = self.store.memberships.resolve_contact_elder_id(principal, elder_id)
        if not resolved_elder_id:
            return self.store.memberships.empty_emergency_contact()
        with self.store.connect() as conn:
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
            return self.store.memberships.empty_emergency_contact(resolved_elder_id)
        return self.store.memberships.public_emergency_contact(row)

    def save_emergency_contact(
        self,
        principal: dict[str, Any],
        elder_id: str = "",
        name: str = "",
        relation: str = "",
        phone: str = "",
    ) -> dict[str, Any]:
        self.store.memberships.require_family_admin(principal)
        resolved_elder_id = self.store.memberships.resolve_contact_elder_id(principal, elder_id)
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
        updated_at = now_iso()
        with self.store.lock, self.store.connect() as conn:
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
                    (name, relation, phone, updated_at, existing["id"]),
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
                    (contact_id, principal["familyId"], resolved_elder_id, name, relation, phone, updated_at, updated_at),
                )
            contact = conn.execute(
                "SELECT * FROM emergency_contacts WHERE id = ?",
                (contact_id,),
            ).fetchone()
        return self.store.memberships.public_emergency_contact(contact)
