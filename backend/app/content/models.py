from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    title: str
    original_filename: str
    file_type: str
    original_path: str
    processed_pdf_path: str | None = None
    page_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class Page(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    document_id: str = Field(foreign_key="document.id", index=True)
    page_number: int
    extracted_text: str = ""
    preview_path: str
    created_at: datetime = Field(default_factory=utc_now)


class NotebookImport(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    title: str
    raw_text: str
    source_filename: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PageSourceRead(SQLModel):
    document_id: str
    filename: str
    page_number: int


class PageRead(SQLModel):
    id: str
    document_id: str
    page_number: int
    extracted_text: str
    preview_url: str
    source: PageSourceRead


class DocumentRead(SQLModel):
    id: str
    course_id: str
    title: str
    original_filename: str
    file_type: str
    page_count: int
    created_at: datetime
    pages: list[PageRead]


class NotebookImportCreate(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    raw_text: str
    source_filename: str | None = Field(default=None, max_length=255)


class NotebookImportRead(SQLModel):
    id: str
    course_id: str
    title: str
    raw_text: str
    source_filename: str | None
    created_at: datetime
