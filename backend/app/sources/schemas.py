from pathlib import Path

from pydantic import model_validator
from sqlmodel import Field, SQLModel

from app.sources.models import SourceKind


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
