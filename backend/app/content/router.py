from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.content.models import (
    Document,
    DocumentRead,
    NotebookImport,
    NotebookImportCreate,
    NotebookImportRead,
    Page,
    PageRead,
    PageSourceRead,
)
from app.content.service import delete_document_files, ingest_document
from app.courses.models import Course
from app.shared.database import session_for
from app.shared.errors import NotFoundError


router = APIRouter(prefix="/api", tags=["content"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


def _require_course(course_id: str, session: Session) -> None:
    if session.get(Course, course_id) is None:
        raise NotFoundError("Course", course_id)


def _page_response(page: Page, document: Document) -> PageRead:
    return PageRead(
        id=page.id,
        document_id=page.document_id,
        page_number=page.page_number,
        extracted_text=page.extracted_text,
        preview_url=f"/api/pages/{page.id}/preview",
        source=PageSourceRead(
            document_id=document.id,
            filename=document.original_filename,
            page_number=page.page_number,
        ),
    )


def _document_response(document: Document, pages: list[Page]) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        course_id=document.course_id,
        title=document.title,
        original_filename=document.original_filename,
        file_type=document.file_type,
        page_count=document.page_count,
        created_at=document.created_at,
        pages=[_page_response(page, document) for page in pages],
    )


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    course_id: str,
    request: Request,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> DocumentRead:
    _require_course(course_id, session)
    document, pages = ingest_document(
        data_dir=request.app.state.data_dir,
        course_id=course_id,
        filename=file.filename or "",
        stream=file.file,
    )
    session.add(document)
    session.add_all(pages)
    session.commit()
    session.refresh(document)
    for page in pages:
        session.refresh(page)
    return _document_response(document, pages)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: str, session: SessionDependency) -> DocumentRead:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    pages = list(
        session.exec(
            select(Page).where(Page.document_id == document_id).order_by(Page.page_number)
        ).all()
    )
    return _document_response(document, pages)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str, request: Request, session: SessionDependency
) -> Response:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    pages = list(session.exec(select(Page).where(Page.document_id == document_id)).all())
    delete_document_files(data_dir=request.app.state.data_dir, document_id=document_id)
    for page in pages:
        session.delete(page)
    session.delete(document)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/courses/{course_id}/documents", response_model=list[DocumentRead])
def list_course_documents(course_id: str, session: SessionDependency) -> list[DocumentRead]:
    _require_course(course_id, session)
    documents = list(
        session.exec(
            select(Document)
            .where(Document.course_id == course_id)
            .order_by(Document.created_at.desc())
        ).all()
    )
    result: list[DocumentRead] = []
    for document in documents:
        pages = list(
            session.exec(
                select(Page)
                .where(Page.document_id == document.id)
                .order_by(Page.page_number)
            ).all()
        )
        result.append(_document_response(document, pages))
    return result


@router.get("/pages/{page_id}/preview", response_class=FileResponse)
def get_page_preview(
    page_id: str, request: Request, session: SessionDependency
) -> FileResponse:
    page = session.get(Page, page_id)
    if page is None:
        raise NotFoundError("Page", page_id)
    preview_path = Path(request.app.state.data_dir, page.preview_path)
    if not preview_path.is_file():
        raise NotFoundError("Page preview", page_id)
    return FileResponse(preview_path, media_type="image/png")


@router.post(
    "/courses/{course_id}/notebook-imports",
    response_model=NotebookImportRead,
    status_code=status.HTTP_201_CREATED,
)
def create_notebook_import(
    course_id: str,
    payload: NotebookImportCreate,
    session: SessionDependency,
) -> NotebookImport:
    _require_course(course_id, session)
    notebook_import = NotebookImport(course_id=course_id, **payload.model_dump())
    session.add(notebook_import)
    session.commit()
    session.refresh(notebook_import)
    return notebook_import
