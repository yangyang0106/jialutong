import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Header, HTTPException

from app.auth_common import FAMILY_ADMIN, SUPER_ADMIN
from app.auth_repository import SqliteAuthRepository
from app.auth_services import (
    ElderBindingService,
    ElderProfileService,
    EmergencyContactService,
    FamilyMembershipService,
    SessionService,
    WechatAuthService,
)


class AuthStore:
    """Thin facade kept stable for routers while auth services are split."""

    def __init__(self, db_path: Path, super_admin_openids: str = "") -> None:
        self.repository = SqliteAuthRepository(db_path)
        self.db_path = self.repository.db_path
        self.lock = Lock()
        self.super_admin_openids_raw = super_admin_openids
        self.memberships = FamilyMembershipService(self)
        self.sessions = SessionService(self)
        self.wechat_auth = WechatAuthService(self)
        self.elder_profiles = ElderProfileService(self)
        self.elder_bindings = ElderBindingService(self)
        self.emergency_contacts = EmergencyContactService(self)

    def connect(self) -> sqlite3.Connection:
        return self.repository.connect()

    def has_users(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return bool(row["count"])

    def status(self) -> dict[str, bool]:
        return {"bootstrapped": self.has_users()}

    def wechat_login(self, openid: str, family_name: str = "我的家庭") -> dict[str, Any]:
        return self.wechat_auth.wechat_login(openid, family_name)

    def wechat_bind_elder(self, openid: str, bind_code: str) -> dict[str, Any]:
        return self.elder_bindings.wechat_bind_elder(openid, bind_code)

    def logout(self, token: str) -> None:
        self.sessions.logout(token)

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        return self.sessions.authenticate(authorization)

    def require_family_admin(self, principal: dict[str, Any]) -> None:
        self.memberships.require_family_admin(principal)

    def me(self, authorization: str | None) -> dict[str, Any]:
        principal = self.authenticate(authorization)
        return {
            "user": principal,
            "elders": self.list_elders(principal),
            "bootstrapped": True,
        }

    def list_elders(self, principal: dict[str, Any]) -> list[dict[str, Any]]:
        return self.elder_profiles.list_elders(principal)

    def create_elder(
        self,
        principal: dict[str, Any],
        name: str,
        phone: str = "",
        note: str = "",
        relation: str = "家属",
    ) -> dict[str, Any]:
        return self.elder_profiles.create_elder(principal, name, phone, note, relation)

    def update_elder(
        self,
        principal: dict[str, Any],
        elder_id: str,
        name: str,
        phone: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        return self.elder_profiles.update_elder(principal, elder_id, name, phone, note)

    def create_elder_bind_code(
        self,
        principal: dict[str, Any],
        elder_id: str,
        relation: str = "本人",
    ) -> dict[str, Any]:
        return self.elder_bindings.create_elder_bind_code(principal, elder_id, relation)

    def bind_elder(self, principal: dict[str, Any], code: str) -> dict[str, Any]:
        return self.elder_bindings.bind_elder(principal, code)

    def get_emergency_contact(
        self, principal: dict[str, Any], elder_id: str = ""
    ) -> dict[str, Any]:
        return self.emergency_contacts.get_emergency_contact(principal, elder_id)

    def save_emergency_contact(
        self,
        principal: dict[str, Any],
        elder_id: str = "",
        name: str = "",
        relation: str = "",
        phone: str = "",
    ) -> dict[str, Any]:
        return self.emergency_contacts.save_emergency_contact(
            principal, elder_id, name, relation, phone
        )

    def load_user(self, conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def load_user_by_wechat_openid(
        self, conn: sqlite3.Connection, openid: str
    ) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE wechat_openid = ?", (openid,)).fetchone()

    def load_elder(self, conn: sqlite3.Connection, elder_id: str) -> sqlite3.Row:
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

    def load_active_bind_code(self, conn: sqlite3.Connection, code: str) -> sqlite3.Row:
        from app.auth_common import now, parse_time

        row = conn.execute("SELECT * FROM elder_bind_codes WHERE code = ?", (code,)).fetchone()
        if not row or row["used_at"]:
            raise HTTPException(status_code=404, detail="绑定码不存在或已使用")
        expires_at = parse_time(row["expires_at"])
        if not expires_at or expires_at <= now():
            raise HTTPException(status_code=410, detail="绑定码已过期，请让家人重新生成")
        return row


def is_super_admin_principal(principal: dict[str, Any]) -> bool:
    return principal.get("role") == SUPER_ADMIN


def require_family_admin(principal: dict[str, Any]) -> None:
    if principal.get("role") not in {FAMILY_ADMIN, SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="只有家庭管理员可以操作")


def family_guard(principal: dict[str, Any], route: dict[str, Any]) -> bool:
    if is_super_admin_principal(principal):
        return True
    family_id = route.get("familyId")
    return bool(family_id and family_id == principal.get("familyId"))


def route_owner_patch(principal: dict[str, Any], route: dict[str, Any] | None = None) -> dict[str, str]:
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
