from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.desktop.instance import APPLICATION_ID
from app.runtime.version import APPLICATION_VERSION
from app.system.schemas import SystemInfo
from app.system.service import (
    create_diagnostics,
    is_setup_complete,
    mark_setup_complete,
    open_directory,
)


router = APIRouter(prefix="/api/system", tags=["system"])


def _setup_complete(request: Request) -> bool:
    settings = request.app.state.ai_settings_service.get()
    if settings.provider == "codex":
        return bool(settings.model.strip())
    return bool(settings.model.strip() and settings.base_url.strip() and settings.api_key_configured)


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


@router.get("/diagnostics")
def diagnostics(request: Request) -> StreamingResponse:
    settings = request.app.state.ai_settings_service.get().model_dump()
    content = create_diagnostics(
        request.app.state.paths,
        packaged=bool(getattr(request.app.state, "packaged", False)),
        settings=settings,
    )
    return StreamingResponse(
        BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="semiconductor-review-diagnostics.zip"'},
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
