from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceQuestion(SQLModel, table=True):
    __tablename__ = "source_question"
    __table_args__ = (
        Index("uq_source_question_document_fingerprint", "document_id", "fingerprint", unique=True),
        Index("ix_source_question_project_id", "project_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    document_id: int = Field(foreign_key="source_document.id")
    question_text: str
    answer_text: str | None = None
    source_block_ids_json: str
    evidence_quotes_json: str = "[]"
    fingerprint: str
    user_edited: bool = False
    archived: bool = False
    run_id: int | None = Field(default=None, foreign_key="analysis_run.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class GeneratedArtifact(SQLModel, table=True):
    __tablename__ = "generated_artifact"
    __table_args__ = (Index("ix_generated_artifact_project_kind", "project_id", "kind"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    kind: str
    status: str = "queued"
    payload_json: str = "{}"
    keypoint_ids_json: str
    source_question_ids_json: str = "[]"
    provider_id: str
    provider_config_generation: int
    provider_protocol: str
    provider_base_url: str
    model_id: str
    prompt_snapshot: str
    prompt_hash: str
    cache_status: str | None = None
    public_error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
