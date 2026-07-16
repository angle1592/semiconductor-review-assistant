from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class KeyPointCandidate(SQLModel, table=True):
    __tablename__ = "keypoint_candidate"
    __table_args__ = (
        Index(
            "uq_keypoint_candidate_run_batch_ordinal",
            "run_id",
            "batch_id",
            "ordinal",
            unique=True,
        ),
        Index("ix_keypoint_candidate_project_id", "project_id"),
        Index("ix_keypoint_candidate_run_id", "run_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    run_id: int = Field(foreign_key="analysis_run.id")
    batch_id: int = Field(foreign_key="analysis_batch.id")
    ordinal: int
    title: str
    explanation: str
    importance: str
    source_block_ids_json: str
    evidence_quotes_json: str
    rationale: str
    status: str = "pending"
    user_edited: bool = False
    confirmed_keypoint_id: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KeyPoint(SQLModel, table=True):
    __tablename__ = "keypoint"
    __table_args__ = (
        Index("uq_keypoint_project_fingerprint", "project_id", "fingerprint", unique=True),
        Index("ix_keypoint_project_position", "project_id", "position"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    title: str
    explanation: str
    importance: str
    source_block_ids_json: str = "[]"
    evidence_quotes_json: str = "[]"
    origin: str = "manual"
    run_id: int | None = None
    user_edited: bool = False
    fingerprint: str
    position: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
