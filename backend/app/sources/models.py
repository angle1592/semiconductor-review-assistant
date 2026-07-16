from datetime import UTC, datetime
from typing import Literal

from sqlmodel import Field, SQLModel


SourceKind = Literal["knowledge", "question_bank", "mixed"]
ParseStatus = Literal["queued", "parsing", "ready", "degraded", "failed"]
BlockKind = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "image",
    "question",
    "answer",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceDocument(SQLModel, table=True):
    __tablename__ = "source_document"

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id", index=True)
    original_name: str
    stored_name: str
    extension: str
    media_type: str
    byte_size: int
    sha256: str = Field(index=True)
    source_kind: str = "mixed"
    parse_status: str = "queued"
    parser_version: str
    page_count: int | None = None
    parse_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SourceBlock(SQLModel, table=True):
    __tablename__ = "source_block"

    id: str = Field(primary_key=True)
    document_id: int = Field(foreign_key="source_document.id", index=True)
    ordinal: int = Field(index=True)
    locator: str
    kind: str
    text: str = ""
    page_number: int | None = None
    heading_path_json: str = "[]"
    asset_path: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
