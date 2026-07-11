from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Lesson(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    title: str
    notes: str = ""
    target_minutes: int = 10
    page_ids_json: str = "[]"
    notebook_import_ids_json: str = "[]"
    status: str = "draft"
    generation_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgePoint(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    lesson_id: str = Field(foreign_key="lesson.id", index=True)
    topic: str
    explanation: str = ""
    source_refs_json: str = "[]"
    created_at: datetime = Field(default_factory=utc_now)


class Question(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    lesson_id: str = Field(foreign_key="lesson.id", index=True)
    knowledge_point_id: str | None = Field(default=None, foreign_key="knowledgepoint.id")
    prompt: str
    reference_answer: str
    explanation: str = ""
    source_refs_json: str = "[]"
    is_bad: bool = False
    stage: int = 0
    due_at: datetime | None = Field(default=None, index=True)
    schedule_status: str = "learning"
    mastery_state: str = "unreviewed"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReviewSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    lesson_id: str | None = Field(default=None, foreign_key="lesson.id", index=True)
    question_ids_json: str
    started_at: datetime = Field(default_factory=utc_now)
    stop_adding_at: datetime
    hard_deadline_at: datetime
    status: str = "active"


class Attempt(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    review_session_id: str = Field(foreign_key="reviewsession.id", index=True)
    question_id: str = Field(foreign_key="question.id", index=True)
    action: str
    answer_text: str = ""
    self_rating: str | None = None
    assessment_verdict: str | None = None
    missing_points_json: str = "[]"
    feedback: str = ""
    outcome: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
