from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.desktop.instance import APPLICATION_ID
from app.diagnostics.service import cache_summary, clear_cache, create_diagnostics
from app.runtime.version import APPLICATION_VERSION
from app.system.schemas import SystemInfo
from app.system.service import (
    is_setup_complete,
    mark_setup_complete,
    open_directory,
)


router = APIRouter(prefix="/api/system", tags=["system"])


class CacheClearRequest(BaseModel):
    expected_bytes: int = Field(ge=0)
    confirmation: str


def _setup_complete(request: Request) -> bool:
    return request.app.state.provider_profile_service.setup_ready()


@router.get("/info", response_model=SystemInfo)
def system_info(request: Request) -> SystemInfo:
    paths = request.app.state.paths
    return SystemInfo(
        application=APPLICATION_ID,
        version=APPLICATION_VERSION,
        packaged=bool(getattr(request.app.state, "packaged", False)),
        setup_complete=is_setup_complete(paths.data),
        data_directory=str(paths.data),
        log_directory=str(paths.logs),
    )


@router.post("/setup-complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_setup(request: Request) -> Response:
    if not _setup_complete(request):
        raise HTTPException(status_code=409, detail="AI configuration is incomplete.")
    mark_setup_complete(request.app.state.paths.data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/paths/{kind}/open", status_code=status.HTTP_204_NO_CONTENT)
def open_system_path(kind: str, request: Request) -> Response:
    paths = request.app.state.paths
    allowed = {"data": paths.data, "backups": paths.backups, "logs": paths.logs}
    path = allowed.get(kind)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown local directory.")
    open_directory(path, getattr(request.app.state, "path_opener", None))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/caches")
def caches(request: Request) -> dict[str, dict[str, int]]:
    return cache_summary(request.app.state.paths)


@router.post("/caches/{kind}/clear")
def clear_cache_endpoint(kind: str, payload: CacheClearRequest, request: Request) -> dict:
    try:
        removed = clear_cache(
            request.app.state.paths,
            kind,
            expected_bytes=payload.expected_bytes,
            confirmation=payload.confirmation,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail="缓存大小已变化或确认信息不匹配，请刷新后重试。",
        ) from error
    return {"cleared": True, "removed": removed, "current": cache_summary(request.app.state.paths)}


@router.get("/diagnostics")
def diagnostics(request: Request) -> StreamingResponse:
    providers = request.app.state.provider_profile_service
    content = create_diagnostics(
        request.app.state.paths,
        packaged=bool(getattr(request.app.state, "packaged", False)),
        provider_summary=providers.diagnostic_summary(),
        known_secrets=providers.diagnostic_secret_values(),
    )
    return StreamingResponse(
        BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="shiyao-diagnostics.zip"'},
    )


@router.post("/shutdown", status_code=status.HTTP_202_ACCEPTED)
def shutdown(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail="Shutdown is only available locally.")
    callback = getattr(request.app.state, "shutdown_callback", None)
    if callback is None:
        raise HTTPException(status_code=409, detail="This process cannot be stopped through the API.")
    background_tasks.add_task(callback)
    return {"status": "stopping"}
