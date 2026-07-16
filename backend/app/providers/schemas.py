from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProviderProtocol = Literal["openai_compatible", "anthropic"]


class ProviderProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: ProviderProtocol
    base_url: str
    api_key: str | None = Field(default=None, exclude=True)


class ProviderProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    protocol: ProviderProtocol | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, exclude=True)


class ProviderProfileRead(BaseModel):
    id: str
    name: str
    protocol: ProviderProtocol
    base_url: str
    enabled: bool
    is_default: bool
    credential_generation: int
    api_key_configured: bool
    models_fetched_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelProfileCreate(BaseModel):
    model_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class ModelProfileRead(ModelProfileCreate):
    id: str
    provider_id: str
    text_status: str
    structured_status: str
    vision_status: str
    prompt_cache_status: str
    safe_error_code: str | None
    validated_at: datetime | None
