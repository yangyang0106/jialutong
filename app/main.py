from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.core.config import load_settings
from app.dependencies import AppContainer


settings = load_settings()
container = AppContainer(settings)


def create_app() -> FastAPI:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="家路通文件与路线配置服务", version="0.1.0")
    app.mount("/files", StaticFiles(directory=settings.upload_dir), name="files")
    container.include_routers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
