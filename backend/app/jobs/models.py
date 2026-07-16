from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


JobStatus = Literal["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class DurableJob(SQLModel, table=True):
    __tablename__ = "durable_job"
    __table_args__ = (Index("ix_durable_job_status_available_at", "status", "available_at"),)

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    payload_json: str
    status: str = "queued"
    attempts: int = 0
    max_attempts: int = 3
    available_at: datetime = Field(default_factory=utc_now)
    worker_id: str | None = Field(default=None, index=True)
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    public_error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
