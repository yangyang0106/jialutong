from threading import Lock
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.schemas import StepConfig
from app.services import file_assets


def create_files_router(
    *,
    require_token,
    upload_dir,
    public_base_url: str,
    routes_lock: Lock,
    load_routes: Callable[[], dict],
    save_routes: Callable[[dict], None],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/files", dependencies=[Depends(require_token)])
    def upload_file(
        file: UploadFile = File(...),
        routeId: str = Form(...),
        stepNo: int = Form(...),
        kind: str = Form(...),
    ) -> dict[str, str]:
        return file_assets.save_uploaded_file(
            file=file,
            upload_dir=upload_dir,
            public_base_url=public_base_url,
            route_id=routeId,
            step_no=stepNo,
            kind=kind,
        )

    @router.delete("/api/files", dependencies=[Depends(require_token)])
    def delete_file(url: str) -> dict[str, bool]:
        return file_assets.delete_uploaded_file(
            url=url,
            upload_dir=upload_dir,
            public_base_url=public_base_url,
        )

    @router.get("/api/routes/{route_id}")
    def get_route_config(route_id: str) -> dict:
        return {"routeId": route_id, "steps": load_routes().get(route_id, {})}

    @router.put("/api/routes/{route_id}/steps/{step_no}", dependencies=[Depends(require_token)])
    def update_step_config(route_id: str, step_no: int, config: StepConfig) -> dict:
        with routes_lock:
            routes = load_routes()
            route = routes.setdefault(route_id, {})
            current = route.setdefault(str(step_no), {})
            current.update(config.model_dump(exclude_none=True))
            save_routes(routes)
        return {"routeId": route_id, "stepNo": step_no, "config": current}

    return router
