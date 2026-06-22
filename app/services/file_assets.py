import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

ALLOWED_CONTENT_TYPES = {
    "image": {"image/jpeg", "image/png", "image/webp"},
    "audio": {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/aac"},
}
MAX_BYTES = {"image": 10 * 1024 * 1024, "audio": 5 * 1024 * 1024}
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
}


def save_uploaded_file(
    *,
    file: UploadFile,
    upload_dir: Path,
    public_base_url: str,
    route_id: str,
    step_no: int,
    kind: str,
) -> dict[str, str]:
    if kind not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="invalid kind")
    if file.content_type not in ALLOWED_CONTENT_TYPES[kind]:
        raise HTTPException(status_code=415, detail="unsupported file type")
    extension = EXTENSIONS[file.content_type]
    route_dir = upload_dir / route_id / str(step_no)
    route_dir.mkdir(parents=True, exist_ok=True)
    destination = route_dir / f"{kind}-{uuid.uuid4().hex}{extension}"
    written = 0
    with destination.open("wb") as output:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_BYTES[kind]:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file too large")
            output.write(chunk)
    relative_path = destination.relative_to(upload_dir).as_posix()
    return {"url": f"{public_base_url}/files/{relative_path}"}


def delete_uploaded_file(
    *,
    url: str,
    upload_dir: Path,
    public_base_url: str,
) -> dict[str, bool]:
    prefix = f"{public_base_url}/files/"
    if not url.startswith(prefix):
        raise HTTPException(status_code=400, detail="invalid file url")
    relative_path = url.removeprefix(prefix)
    target = (upload_dir / relative_path).resolve()
    if upload_dir.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="invalid file path")
    target.unlink(missing_ok=True)
    return {"deleted": True}
