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


class KeyPointCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=5000)
    importance: Literal["core", "important", "supplementary"]
    source_block_ids: list[str] = Field(min_length=1)
    evidence_quotes: list[str]
    rationale: str = Field(min_length=1, max_length=2000)


class ExtractedQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    answer: str | None = Field(default=None, max_length=10000)
    source_block_ids: list[str] = Field(min_length=1)
    evidence_quotes: list[str]


class AnalysisBatchResult(BaseModel):
    candidates: list[KeyPointCandidate]
    source_questions: list[ExtractedQuestion]
