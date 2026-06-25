from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.services import file_assets


def create_files_router(
    *,
    require_token,
    upload_dir,
    public_base_url: str,
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

    return router
