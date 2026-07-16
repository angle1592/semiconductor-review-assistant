from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.shared.database import session_for
from app.sources.models import SourceKind
from app.sources.schemas import (
    DeletionImpact,
    DeletionResult,
    SourceBlockListRead,
    SourceDocumentRead,
    SourceDocumentUpdate,
    SourceListRead,
    SourceUploadRead,
)
from app.sources.service import (
    block_read,
    delete_source,
    get_source,
    ingest_source,
    list_source_blocks,
    list_sources,
    preview_asset,
    source_deletion_impact,
    source_read,
    update_source,
)


router = APIRouter(tags=["sources"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


@router.post(
    "/api/projects/{project_id}/sources",
    response_model=SourceUploadRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_source_endpoint(
    request: Request,
    project_id: str,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
    source_kind: Annotated[SourceKind, Form()] = "mixed",
):
    return ingest_source(
        session,
        project_id=project_id,
        filename=file.filename,
        media_type=file.content_type,
        source_kind=source_kind,
        stream=file.file,
        data_dir=request.app.state.paths.data,
        parser=request.app.state.source_parsing_service,
        max_bytes=request.app.state.source_max_bytes,
    )


@router.get("/api/projects/{project_id}/sources", response_model=SourceListRead)
def list_sources_endpoint(
    project_id: str,
    session: SessionDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    documents, total = list_sources(session, project_id, offset=offset, limit=limit)
    return {
        "items": [source_read(document) for document in documents],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/sources/{source_id}", response_model=SourceDocumentRead)
def get_source_endpoint(source_id: int, session: SessionDependency):
    return source_read(get_source(session, source_id))


@router.get("/api/sources/{source_id}/blocks", response_model=SourceBlockListRead)
def list_source_blocks_endpoint(
    source_id: int,
    session: SessionDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    blocks, total = list_source_blocks(session, source_id, offset=offset, limit=limit)
    return {
        "items": [block_read(block) for block in blocks],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/sources/{source_id}/preview/{asset_path:path}")
def preview_source_asset_endpoint(
    request: Request,
    source_id: int,
    asset_path: str,
    session: SessionDependency,
):
    document = get_source(session, source_id)
    path = preview_asset(document, request.app.state.paths.data, asset_path)
    return FileResponse(path)


@router.patch("/api/sources/{source_id}", response_model=SourceDocumentRead)
def update_source_endpoint(
    source_id: int,
    payload: SourceDocumentUpdate,
    session: SessionDependency,
):
    return source_read(update_source(session, source_id, payload))


@router.get("/api/sources/{source_id}/deletion-impact", response_model=DeletionImpact)
def source_deletion_impact_endpoint(
    request: Request,
    source_id: int,
    session: SessionDependency,
):
    return source_deletion_impact(session, source_id, request.app.state.paths.data)


@router.delete("/api/sources/{source_id}", response_model=DeletionResult)
def delete_source_endpoint(
    request: Request,
    source_id: int,
    session: SessionDependency,
):
    impact = delete_source(
        session,
        source_id,
        data_dir=request.app.state.paths.data,
        runtime_dir=request.app.state.paths.runtime,
    )
    return {"deleted": impact}
