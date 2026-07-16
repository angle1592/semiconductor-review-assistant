from typing import Literal

from pydantic import BaseModel, Field


class AnalysisRunSnapshot(BaseModel):
    project_id: str
    selected_block_ids: list[str] = Field(min_length=1)
    prompt_snapshot: str
    provider_id: str
    provider_config_generation: int = Field(ge=1)
    model_id: str
    schema_version: str
    pipeline_version: str


class AnalysisProgress(BaseModel):
    status: Literal["queued", "running", "partial", "succeeded", "failed", "cancelled"]
    total_batches: int
    completed_batches: int
    failed_batches: int
