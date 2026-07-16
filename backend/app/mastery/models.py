from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class StudyAttempt(SQLModel, table=True):
    __tablename__ = "study_attempt"
    __table_args__ = (Index("ix_study_attempt_project_created", "project_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    mode: str
    item_type: str
    item_id: int
    response_json: str | None = None
    correct: bool | None = None
    self_rating: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class MasteryRecord(SQLModel, table=True):
    __tablename__ = "mastery_record"
    __table_args__ = (
        Index("uq_mastery_project_target", "project_id", "target_type", "target_id", unique=True),
        Index("ix_mastery_project_level", "project_id", "level"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id")
    target_type: str
    target_id: int
    level: str = "unrated"
    last_attempt_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)
