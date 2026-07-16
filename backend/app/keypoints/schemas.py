from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Importance = Literal["core", "important", "supplementary"]


class CandidateRead(BaseModel):
    id: int
    project_id: str
    run_id: int
    batch_id: int
    title: str
    explanation: str
    importance: Importance
    source_block_ids: list[str]
    evidence_quotes: list[str]
    rationale: str
    status: Literal["pending", "confirmed", "rejected"]
    user_edited: bool
    confirmed_keypoint_id: int | None
    created_at: datetime
    updated_at: datetime


class CandidateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    explanation: str | None = Field(default=None, min_length=1, max_length=5000)
    importance: Importance | None = None
    rationale: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reject_nulls(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null")
        return self


class CandidateBulkAction(BaseModel):
    confirm_ids: list[int] = Field(default_factory=list)
    reject_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disjoint(self):
        if set(self.confirm_ids) & set(self.reject_ids):
            raise ValueError("同一候选不能同时确认和拒绝")
        if not self.confirm_ids and not self.reject_ids:
            raise ValueError("至少选择一个候选")
        return self


class CandidateBulkResult(BaseModel):
    confirmed: int
    rejected: int
    keypoint_ids: list[int]


class KeyPointFields(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=5000)
    importance: Importance
    source_block_ids: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)


class KeyPointCreate(KeyPointFields):
    pass


class KeyPointUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    explanation: str | None = Field(default=None, min_length=1, max_length=5000)
    importance: Importance | None = None
    source_block_ids: list[str] | None = None
    evidence_quotes: list[str] | None = None

    @model_validator(mode="after")
    def reject_nulls(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null")
        return self


class KeyPointRead(KeyPointFields):
    id: int
    project_id: str
    origin: Literal["manual", "ai"]
    run_id: int | None
    user_edited: bool
    position: int
    created_at: datetime
    updated_at: datetime


class KeyPointReorder(BaseModel):
    ordered_ids: list[int]
