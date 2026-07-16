import hashlib
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.backup.service import create_backup, restore_backup, validate_backup
from app.runtime.version import APPLICATION_VERSION


router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("/export")
def export_backup(request: Request) -> StreamingResponse:
    content = create_backup(request.app.state.data_dir, APPLICATION_VERSION)
    headers = {"Content-Disposition": 'attachment; filename="shiyao-backup.zip"'}
    return StreamingResponse(BytesIO(content), media_type="application/zip", headers=headers)


@router.post("/validate")
async def validate_backup_endpoint(
    file: Annotated[UploadFile, File()],
) -> dict:
    content = await file.read()
    manifest, errors = validate_backup(content)
    return {
        "valid": not errors,
        "archive_sha256": hashlib.sha256(content).hexdigest(),
        "manifest": manifest,
        "errors": errors,
    }


@router.post("/restore")
async def restore_backup_endpoint(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict:
    content = await file.read()
    manifest = restore_backup(content, request.app.state.data_dir, request.app.state.database)
    return {"restored": True, "requires_restart": True, "manifest": manifest}
