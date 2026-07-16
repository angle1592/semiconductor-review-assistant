from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReviewProjectFields(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    importance_prompt: str = Field(default="", max_length=10000)


class ReviewProject(ReviewProjectFields, table=True):
    __tablename__ = "review_project"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReviewProjectCreate(ReviewProjectFields):
    pass


class ReviewProjectUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    importance_prompt: str | None = Field(default=None, max_length=10000)


class ReviewProjectRead(ReviewProjectFields):
    id: str
    created_at: datetime
    updated_at: datetime
