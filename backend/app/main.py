import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.ai.router import router as ai_router
from app.ai.secrets import SecretStore, WindowsKeyringSecretStore
from app.ai.settings import AISettingsService, ProviderFactory, default_provider_factory
from app.content.router import router as content_router
from app.courses.router import router as courses_router
from app.backup.router import router as backup_router
from app.learning.provider import ProviderFactory as LearningProviderFactory
from app.learning.ai_adapter import LearningAIAdapter
from app.learning.router import router as learning_router
from app.shared.database import create_database
from app.shared.errors import AppError, app_error_handler, unexpected_error_handler
from app.shared.request_id import RequestIdMiddleware


def create_app(
    data_dir: str | Path,
    *,
    secret_store: SecretStore | None = None,
    ai_provider_factory: ProviderFactory = default_provider_factory,
    learning_provider_factory: LearningProviderFactory | None = None,
    frontend_dist_dir: str | Path | None = None,
) -> FastAPI:
    resolved_data_dir = Path(data_dir).resolve()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            application.state.database.dispose()

    app = FastAPI(title="Semiconductor Review Assistant", lifespan=lifespan)
    app.state.data_dir = resolved_data_dir
    app.state.database = create_database(resolved_data_dir)
    app.state.ai_settings_service = AISettingsService(
        app.state.database,
        resolved_data_dir,
        secret_store or WindowsKeyringSecretStore(),
        ai_provider_factory,
    )
    def default_learning_provider():
        return LearningAIAdapter(app.state.ai_settings_service.create_provider())

    app.state.ai_provider_factory = learning_provider_factory or default_learning_provider
    if learning_provider_factory is None:
        app.state.ai_answer_assessor = default_learning_provider

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(courses_router)
    app.include_router(content_router)
    app.include_router(ai_router)
    app.include_router(learning_router)
    app.include_router(backup_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        try:
            with app.state.database.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "ok", "checks": {"database": "ok"}}
        except Exception as error:
            raise HTTPException(status_code=503, detail="Database is unavailable.") from error

    if frontend_dist_dir is not None:
        frontend_dir = Path(frontend_dist_dir).resolve()
        assets_dir = frontend_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend_spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found.")
            index = frontend_dir / "index.html"
            if not index.is_file():
                raise HTTPException(status_code=404, detail="Frontend build not found.")
            return FileResponse(index)

    return app


def create_default_app() -> FastAPI:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.getenv("SEMIREVIEW_DATA_DIR", project_root / "data"))
    frontend_dir = Path(os.getenv("SEMIREVIEW_FRONTEND_DIST", project_root / "frontend" / "dist"))
    return create_app(data_dir=data_dir, frontend_dist_dir=frontend_dir)
