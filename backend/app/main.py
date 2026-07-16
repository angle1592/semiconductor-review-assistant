from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.backup.router import router as backup_router
from app.providers.credentials import SecretStore, WindowsKeyringSecretStore
from app.providers.router import router as providers_router
from app.providers.service import AdapterFactory, ProviderProfileService, default_adapter_factory
from app.projects.router import router as projects_router
from app.shared.database import create_database
from app.shared.errors import AppError, app_error_handler, unexpected_error_handler
from app.shared.request_id import RequestIdMiddleware
from app.runtime.migrations import migrate_database
from app.runtime.identity import APPLICATION_ID, DATABASE_NAME, PROTOCOL_VERSION
from app.runtime.paths import AppPaths
from app.system.router import router as system_router


logger = logging.getLogger(__name__)


def create_app(
    data_dir: str | Path,
    *,
    secret_store: SecretStore | None = None,
    provider_adapter_factory: AdapterFactory = default_adapter_factory,
    frontend_dist_dir: str | Path | None = None,
) -> FastAPI:
    resolved_data_dir = Path(data_dir).resolve()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            application.state.database.dispose()

    app = FastAPI(title="Shiyao Review", lifespan=lifespan)
    app.state.data_dir = resolved_data_dir
    app.state.paths = AppPaths(
        root=resolved_data_dir.parent,
        data=resolved_data_dir,
        backups=resolved_data_dir.parent / "Backups",
        logs=resolved_data_dir.parent / "Logs",
        runtime=resolved_data_dir.parent / "Runtime",
        frontend_dist=Path(frontend_dist_dir).resolve() if frontend_dist_dir else resolved_data_dir.parent / "frontend" / "dist",
    )
    app.state.packaged = False
    app.state.database = create_database(resolved_data_dir)
    app.state.provider_profile_service = ProviderProfileService(
        app.state.database, secret_store or WindowsKeyringSecretStore(), provider_adapter_factory
    )
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
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.info(
                "request path=%s status=500 duration_ms=%.1f",
                request.url.path,
                (time.perf_counter() - started) * 1000,
            )
            raise
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        logger.info(
            "request path=%s status=%s duration_ms=%.1f",
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(projects_router)
    app.include_router(providers_router)
    app.include_router(backup_router)
    app.include_router(system_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        try:
            with app.state.database.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {
                "application": APPLICATION_ID,
                "protocol_version": PROTOCOL_VERSION,
                "status": "ok",
                "checks": {"database": "ok"},
            }
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
    paths = AppPaths.discover()
    paths.ensure_directories()
    migrate_database(paths.data / DATABASE_NAME, paths.backups)
    app = create_app(data_dir=paths.data, frontend_dist_dir=paths.frontend_dist)
    app.state.paths = paths
    return app
