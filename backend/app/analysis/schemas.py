from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class AnalysisScope(BaseModel):
    mode: Literal["selected_blocks", "all_sources"]
    block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.mode == "all_sources" and self.block_ids:
            raise ValueError("all_sources 不接受 block_ids")
        return self


class AnalysisRunCreate(BaseModel):
    scope: AnalysisScope
    provider_id: str = Field(min_length=1)
    model_profile_id: str = Field(min_length=1)
    run_override: str = Field(default="", max_length=10000)
    parameters: dict[str, object] = Field(default_factory=lambda: {"temperature": 0})
    confirm_large_range: bool = False


class AnalysisRangeEstimate(BaseModel):
    source_count: int
    block_count: int
    page_count: int
    character_count: int
    image_count: int
    exceeds_warning: bool


class AnalysisRunCreated(BaseModel):
    run_id: int
    job_id: int
    status: str
    batch_count: int
    message: str


class AnalysisBatchRead(BaseModel):
    id: int
    ordinal: int
    status: str
    attempts: int
    cache_status: str | None
    public_error_code: str | None
    error_detail: str | None


class AnalysisRunRead(BaseModel):
    id: int
    project_id: str
    status: str
    total_batches: int
    completed_batches: int
    failed_batches: int
    cancellation_requested: bool
    public_error_code: str | None
    error_detail: str | None
    batches: list[AnalysisBatchRead]


class AnalysisCancelRead(BaseModel):
    run_id: int
    status: str
    cancellation_requested: bool


class AnalysisRetryRead(BaseModel):
    run_id: int
    job_id: int
    status: str
    retried_batch_ids: list[int]
