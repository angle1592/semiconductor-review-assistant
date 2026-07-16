from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


RunStatus = Literal["queued", "running", "partial", "succeeded", "failed", "cancelled"]
BatchStatus = Literal["queued", "running", "succeeded", "failed", "skipped"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class AnalysisRun(SQLModel, table=True):
    __tablename__ = "analysis_run"
    __table_args__ = (Index("ix_analysis_run_project_id", "project_id"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    status: str = "queued"
    selected_block_ids_json: str
    prompt_snapshot: str
    provider_id: str
    provider_config_generation: int
    model_id: str
    schema_version: str
    pipeline_version: str
    total_batches: int = 0
    completed_batches: int = 0
    failed_batches: int = 0
    cancellation_requested: bool = False
    public_error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalysisBatch(SQLModel, table=True):
    __tablename__ = "analysis_batch"
    __table_args__ = (Index("ix_analysis_batch_run_id", "run_id"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="analysis_run.id")
    ordinal: int
    status: str = "queued"
    block_ids_json: str
    attempts: int = 0
    result_json: str | None = None
    public_error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
