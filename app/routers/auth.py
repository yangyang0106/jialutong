from typing import Callable

from fastapi import APIRouter, Depends, Header

from app.schemas import (
    AuthWechatBindElderRequest,
    AuthWechatLoginRequest,
    ElderBindCodeRequest,
    ElderBindRequest,
    ElderProfileRequest,
    EmergencyContactRequest,
)


def create_auth_router(
    *,
    auth_status: Callable[[], dict],
    auth_wechat_login: Callable[[str, str], dict],
    auth_wechat_bind_elder: Callable[[str, str], dict],
    auth_logout: Callable[[str], None],
    auth_me: Callable[[str | None], dict],
    require_token,
    list_elders: Callable[[dict], list[dict]],
    create_elder: Callable[[dict, str, str, str, str], dict],
    update_elder: Callable[[dict, str, str, str, str], dict],
    create_elder_bind_code: Callable[[dict, str, str], dict],
    bind_elder: Callable[[dict, str], dict],
    get_emergency_contact: Callable[[dict, str], dict],
    save_emergency_contact: Callable[[dict, str, str, str, str], dict],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/auth/status")
    def status() -> dict:
        return auth_status()


    @router.post("/api/auth/wechat-login")
    def wechat_login(request: AuthWechatLoginRequest) -> dict:
        return auth_wechat_login(request.code, request.familyName)

    @router.post("/api/auth/wechat-bind-elder")
    def wechat_bind_elder(request: AuthWechatBindElderRequest) -> dict:
        return auth_wechat_bind_elder(request.code, request.bindCode)

    @router.post("/api/auth/logout")
    def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
        token = ""
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
        if token:
            auth_logout(token)
        return {"ok": True}

    @router.get("/api/auth/me")
    def me(authorization: str | None = Header(default=None)) -> dict:
        return auth_me(authorization)

    @router.get("/api/auth/elders")
    def elders(principal: dict = Depends(require_token)) -> dict:
        return {"elders": list_elders(principal)}

    @router.post("/api/auth/elders")
    def add_elder(
        request: ElderProfileRequest, principal: dict = Depends(require_token)
    ) -> dict:
        return create_elder(
            principal,
            request.name,
            request.phone,
            request.note,
            request.relation,
        )

    @router.post("/api/auth/elder-bind-codes")
    def create_bind_code(
        request: ElderBindCodeRequest, principal: dict = Depends(require_token)
    ) -> dict:
        return create_elder_bind_code(principal, request.elderId, request.relation)

    @router.post("/api/auth/elder-bindings")
    def bind_current_user_to_elder(
        request: ElderBindRequest, principal: dict = Depends(require_token)
    ) -> dict:
        return bind_elder(principal, request.code)

    @router.get("/api/auth/emergency-contact")
    def read_emergency_contact(
        elderId: str = "", principal: dict = Depends(require_token)
    ) -> dict:
        return get_emergency_contact(principal, elderId)

    @router.put("/api/auth/emergency-contact")
    def update_emergency_contact(
        request: EmergencyContactRequest, principal: dict = Depends(require_token)
    ) -> dict:
        return save_emergency_contact(
            principal,
            request.elderId,
            request.name,
            request.relation,
            request.phone,
        )

    @router.put("/api/auth/elders/{elder_id}")
    def edit_elder(
        elder_id: str,
        request: ElderProfileRequest,
        principal: dict = Depends(require_token),
    ) -> dict:
        return update_elder(principal, elder_id, request.name, request.phone, request.note)

    return router
