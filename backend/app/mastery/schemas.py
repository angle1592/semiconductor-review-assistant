from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MasteryLevel = Literal["unrated", "learning", "familiar", "mastered"]
StudyMode = Literal["outline", "flashcards", "source_questions", "ai_questions"]
TargetType = Literal["keypoint", "source_question", "artifact"]


class StudyAttemptCreate(BaseModel):
    mode: StudyMode
    item_type: TargetType
    item_id: int = Field(gt=0)
    response: dict | None = None
    correct: bool | None = None
    self_rating: MasteryLevel | None = None


class StudyAttemptRead(BaseModel):
    id: int
    project_id: str
    mode: StudyMode
    item_type: TargetType
    item_id: int
    response: dict | None
    correct: bool | None
    self_rating: MasteryLevel | None
    created_at: datetime


class MasteryUpdate(BaseModel):
    level: MasteryLevel


class MasteryRead(BaseModel):
    id: int
    project_id: str
    target_type: TargetType
    target_id: int
    level: MasteryLevel
    last_attempt_at: datetime | None
    updated_at: datetime


class MasterySummary(BaseModel):
    total: int
    by_level: dict[str, int]
    by_type: dict[str, int]
