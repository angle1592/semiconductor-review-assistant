from pathlib import Path
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field as PydanticField, model_validator
from sqlmodel import Field, SQLModel

from app.sources.models import ParseStatus, SourceKind


SUPPORTED_SOURCE_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"})


class SourceDocumentCreate(SQLModel):
    project_id: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    source_kind: SourceKind = "mixed"
    extension: str = ""

    @model_validator(mode="after")
    def validate_extension(self):
        extension = Path(self.filename).suffix.lower()
        if extension not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError("不支持的资料格式")
        self.extension = extension
        return self


class SourceDocumentRead(BaseModel):
    id: int
    project_id: str
    display_name: str
    extension: str
    media_type: str
    byte_size: int
    sha256: str
    source_kind: SourceKind
    parse_status: ParseStatus
    parser_version: str
    page_count: int | None
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class SourceDocumentUpdate(BaseModel):
    display_name: str | None = PydanticField(default=None, min_length=1, max_length=255)
    source_kind: SourceKind | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for field in ("display_name", "source_kind"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null")
        return self


class SourceBlockRead(BaseModel):
    id: str
    ordinal: int
    locator: str
    kind: str
    text: str
    page_number: int | None
    heading_path: list[str]
    preview_path: str | None


class SourceUploadRead(BaseModel):
    source_id: int
    parse_status: ParseStatus
    page_count: int | None
    block_count: int
    cache: Literal["hit", "miss"]
    warnings: list[str]


class SourceListRead(BaseModel):
    items: list[SourceDocumentRead]
    total: int
    offset: int
    limit: int


class SourceBlockListRead(BaseModel):
    items: list[SourceBlockRead]
    total: int
    offset: int
    limit: int


class DeletionImpact(BaseModel):
    sources: int = 0
    blocks: int = 0
    preview_assets: int = 0
    candidates: int = 0
    source_questions: int = 0
    generated_artifacts: int = 0

    def __add__(self, other: "DeletionImpact") -> "DeletionImpact":
        return DeletionImpact(
            **{
                field: getattr(self, field) + getattr(other, field)
                for field in type(self).model_fields
            }
        )


class DeletionResult(BaseModel):
    deleted: DeletionImpact
