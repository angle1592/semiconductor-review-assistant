from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderCapabilities(BaseModel):
    text: bool
    vision: bool
    structured_output: bool

    def names(self) -> list[str]:
        return [
            name
            for name in ("text", "vision", "structured_output")
            if getattr(self, name)
        ]


class GeneratedLearningItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    question: str
    reference_answer: str
    explanation: str
    source_refs: list[str] = Field(min_length=1)


class AnswerAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["correct", "partial", "incorrect", "unknown"]
    missing_points: list[str]
    feedback: str


class GeneratedLearningItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GeneratedLearningItem] = Field(min_length=1, max_length=8)


class LearningSourcePage(BaseModel):
    source_ref: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    extracted_text: str = ""
    image_path: Path | None = None


class LearningGenerationRequest(BaseModel):
    pages: list[LearningSourcePage] = Field(default_factory=list)
    teacher_emphasis: str = ""
    practice_content: str = ""
    personal_questions: str = ""
    notebook_text: str = ""
    item_count: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def require_source_content(self):
        if not self.pages and not self.notebook_text.strip():
            raise ValueError("At least one page or NotebookLM text source is required.")
        return self


class AnswerAssessmentRequest(BaseModel):
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    user_answer: str
    source_refs: list[str] = []


class ConnectionTestResult(BaseModel):
    ok: bool
    available: bool = True
    message: str
    capabilities: list[str] = []
    error_code: str | None = None
