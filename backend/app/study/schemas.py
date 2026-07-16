from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ArtifactKind = Literal["outline", "flashcard", "ai_new", "ai_variant", "ai_error_cause"]


class SourceQuestionRead(BaseModel):
    id: int
    project_id: str
    document_id: int
    question_text: str
    answer_text: str | None
    source_block_ids: list[str]
    evidence_quotes: list[str]
    user_edited: bool
    archived: bool
    run_id: int | None
    created_at: datetime
    updated_at: datetime


class SourceQuestionUpdate(BaseModel):
    question_text: str | None = Field(default=None, min_length=1, max_length=5000)
    answer_text: str | None = Field(default=None, max_length=10000)


class OutlineSection(BaseModel):
    heading: str
    body: str
    keypoint_ids: list[int]


class OutlinePayload(BaseModel):
    title: str
    sections: list[OutlineSection]


class FlashcardPayload(BaseModel):
    front: str
    back: str
    keypoint_ids: list[int]


class PracticeQuestionPayload(BaseModel):
    question: str
    answer: str
    explanation: str
    origin: Literal["ai_new", "ai_variant", "ai_error_cause"]
    source_question_ids: list[int]
    keypoint_ids: list[int]


class ArtifactGenerationResult(BaseModel):
    outline: OutlinePayload | None = None
    flashcards: list[FlashcardPayload] = Field(default_factory=list)
    questions: list[PracticeQuestionPayload] = Field(default_factory=list)


class ArtifactCreate(BaseModel):
    kind: ArtifactKind
    keypoint_ids: list[int] = Field(min_length=1)
    source_question_ids: list[int] = Field(default_factory=list)
    provider_id: str = Field(min_length=1)
    model_profile_id: str = Field(min_length=1)
    run_override: str = Field(default="", max_length=10000)

class ArtifactRead(BaseModel):
    id: int
    project_id: str
    kind: ArtifactKind
    status: str
    payload: dict
    keypoint_ids: list[int]
    source_question_ids: list[int]
    cache_status: str | None
    public_error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
