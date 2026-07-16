from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class AIProviderProfile(SQLModel, table=True):
    __tablename__ = "ai_provider_profile"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(min_length=1, max_length=100)
    protocol: str = Field(index=True)
    base_url: str
    enabled: bool = False
    is_default: bool = False
    credential_generation: int = 1
    models_fetched_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ModelProfile(SQLModel, table=True):
    __tablename__ = "model_profile"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    provider_id: str = Field(foreign_key="ai_provider_profile.id", index=True)
    model_id: str
    display_name: str
    text_status: str = "untested"
    structured_status: str = "untested"
    vision_status: str = "untested"
    prompt_cache_status: str = "untested"
    safe_error_code: str | None = None
    validated_at: datetime | None = None
