import asyncio
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping

from fastapi import APIRouter, Depends, Request, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session, select

from app.content.models import Document, NotebookImport, Page
from app.courses.models import Course
from app.learning.errors import (
    AnswerAlreadyRecordedError,
    GenerationFailedError,
    InvalidSelfRatingError,
    ProviderUnavailableError,
    QuestionNotInSessionError,
    ReviewSessionExpiredError,
    SourceCourseMismatchError,
    SourceSelectionRequiredError,
    VisionUnsupportedError,
)
from app.learning.models import Attempt, KnowledgePoint, Lesson, Question, ReviewSession
from app.learning.provider import LearningGenerationRequest, LearningSource, ProviderFactory
from app.review.schedule import ReviewOutcome, schedule_next
from app.shared.database import session_for
from app.shared.errors import AppError, NotFoundError


router = APIRouter(prefix="/api", tags=["learning"])


class LessonCreate(BaseModel):
    course_id: str
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=5000)
    target_minutes: int = Field(default=10, ge=5, le=15)
    page_ids: list[str] = Field(default_factory=list)
    notebook_import_ids: list[str] = Field(default_factory=list)


class ReviewSessionCreate(BaseModel):
    lesson_id: str | None = None


class AssessmentInput(BaseModel):
    verdict: Literal["correct", "partial", "incorrect", "unknown"]
    missing_points: list[str] = Field(default_factory=list)
    feedback: str = ""


class AnswerCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question_id: str
    action: Literal["answered", "skipped", "bad"]
    answer_text: str = ""
    self_rating: str | None = Field(
        default=None,
        validation_alias=AliasChoices("selfRating", "self_rating"),
        serialization_alias="selfRating",
    )
    assessment: AssessmentInput | None = None

    @model_validator(mode="after")
    def answered_requires_rating(self):
        if self.action == "answered" and not self.self_rating:
            raise ValueError("answered questions require selfRating")
        return self


class QuestionPatch(BaseModel):
    prompt: str | None = Field(default=None, min_length=1)
    reference_answer: str | None = Field(default=None, min_length=1)
    explanation: str | None = None
    source_refs: list[str] | None = None
    is_bad: bool | None = None


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


def _now(request: Request) -> datetime:
    provider = getattr(request.app.state, "now_provider", None)
    value = provider() if provider is not None else datetime.now(UTC)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value is not None else None


def _load_ids(value: str) -> list[str]:
    loaded = json.loads(value)
    return [str(item) for item in loaded]


def _lesson_response(session: Session, lesson: Lesson) -> dict[str, Any]:
    knowledge_points = list(
        session.exec(
            select(KnowledgePoint)
            .where(KnowledgePoint.lesson_id == lesson.id)
            .order_by(KnowledgePoint.created_at)
        ).all()
    )
    questions = list(
        session.exec(
            select(Question)
            .where(Question.lesson_id == lesson.id)
            .order_by(Question.created_at)
        ).all()
    )
    return {
        "id": lesson.id,
        "course_id": lesson.course_id,
        "title": lesson.title,
        "notes": lesson.notes,
        "target_minutes": lesson.target_minutes,
        "page_ids": _load_ids(lesson.page_ids_json),
        "notebook_import_ids": _load_ids(lesson.notebook_import_ids_json),
        "status": lesson.status,
        "generation_error": lesson.generation_error,
        "created_at": _iso(lesson.created_at),
        "updated_at": _iso(lesson.updated_at),
        "knowledge_points": [
            {
                "id": point.id,
                "topic": point.topic,
                "explanation": point.explanation,
                "source_refs": _load_ids(point.source_refs_json),
            }
            for point in knowledge_points
        ],
        "questions": [_question_response(question) for question in questions],
    }


def _question_response(question: Question) -> dict[str, Any]:
    return {
        "id": question.id,
        "lesson_id": question.lesson_id,
        "knowledge_point_id": question.knowledge_point_id,
        "prompt": question.prompt,
        "reference_answer": question.reference_answer,
        "explanation": question.explanation,
        "source_refs": _load_ids(question.source_refs_json),
        "is_bad": question.is_bad,
        "stage": question.stage,
        "due_at": _iso(question.due_at),
        "schedule_status": question.schedule_status,
        "mastery_state": question.mastery_state,
    }


def _source_response(session: Session, source_ref: str) -> dict[str, Any]:
    kind, separator, source_id = source_ref.partition(":")
    if not separator:
        return {"kind": "unknown", "source_ref": source_ref}
    if kind == "page":
        page = session.get(Page, source_id)
        if page is not None:
            document = session.get(Document, page.document_id)
            if document is not None:
                return {
                    "kind": "page",
                    "source_ref": source_ref,
                    "document_id": document.id,
                    "page_id": page.id,
                    "filename": document.original_filename,
                    "page_number": page.page_number,
                    "preview_url": f"/api/pages/{page.id}/preview",
                }
    if kind == "notebook":
        notebook = session.get(NotebookImport, source_id)
        if notebook is not None:
            return {
                "kind": "notebook",
                "source_ref": source_ref,
                "notebook_import_id": notebook.id,
                "title": notebook.title,
                "filename": notebook.source_filename or notebook.title,
            }
    return {"kind": kind or "unknown", "source_ref": source_ref}


def _hidden_question_response(session: Session, question: Question) -> dict[str, Any]:
    source_refs = _load_ids(question.source_refs_json)
    return {
        "id": question.id,
        "lesson_id": question.lesson_id,
        "prompt": question.prompt,
        "source_refs": source_refs,
        "sources": [_source_response(session, source_ref) for source_ref in source_refs],
        "is_bad": question.is_bad,
    }


def _review_response(session: Session, review: ReviewSession) -> dict[str, Any]:
    questions = [
        question
        for question_id in _load_ids(review.question_ids_json)
        if (question := session.get(Question, question_id)) is not None
    ]
    return {
        "id": review.id,
        "lesson_id": review.lesson_id,
        "status": review.status,
        "started_at": _iso(review.started_at),
        "stop_adding_at": _iso(review.stop_adding_at),
        "hard_deadline_at": _iso(review.hard_deadline_at),
        "questions": [_hidden_question_response(session, question) for question in questions],
    }


def _validate_sources(session: Session, payload: LessonCreate) -> tuple[list[str], list[str]]:
    page_ids = list(dict.fromkeys(payload.page_ids))
    notebook_ids = list(dict.fromkeys(payload.notebook_import_ids))
    if not page_ids and not notebook_ids:
        raise SourceSelectionRequiredError()

    for page_id in page_ids:
        page = session.get(Page, page_id)
        if page is None:
            raise NotFoundError("Page", page_id)
        document = session.get(Document, page.document_id)
        if document is None or document.course_id != payload.course_id:
            raise SourceCourseMismatchError()
    for notebook_id in notebook_ids:
        notebook = session.get(NotebookImport, notebook_id)
        if notebook is None:
            raise NotFoundError("Notebook import", notebook_id)
        if notebook.course_id != payload.course_id:
            raise SourceCourseMismatchError()
    return page_ids, notebook_ids


@router.post("/lessons", status_code=status.HTTP_201_CREATED)
def create_lesson(
    payload: LessonCreate, request: Request, session: SessionDependency
) -> dict[str, Any]:
    if session.get(Course, payload.course_id) is None:
        raise NotFoundError("Course", payload.course_id)
    page_ids, notebook_ids = _validate_sources(session, payload)
    now = _now(request)
    lesson = Lesson(
        course_id=payload.course_id,
        title=payload.title,
        notes=payload.notes,
        target_minutes=payload.target_minutes,
        page_ids_json=json.dumps(page_ids),
        notebook_import_ids_json=json.dumps(notebook_ids),
        status="draft",
        created_at=now,
        updated_at=now,
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return _lesson_response(session, lesson)


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str, session: SessionDependency) -> dict[str, Any]:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise NotFoundError("Lesson", lesson_id)
    return _lesson_response(session, lesson)


def _capability(capabilities: Any, name: str) -> bool:
    if isinstance(capabilities, Mapping):
        return bool(capabilities.get(name, False))
    return bool(getattr(capabilities, name, False))


def _build_generation_request(
    lesson: Lesson,
    request: Request,
    session: Session,
    *,
    include_page_images: bool = True,
) -> LearningGenerationRequest:
    sources: list[LearningSource] = []
    for page_id in _load_ids(lesson.page_ids_json):
        page = session.get(Page, page_id)
        if page is None:
            raise NotFoundError("Page", page_id)
        document = session.get(Document, page.document_id)
        if document is None:
            raise NotFoundError("Document", page.document_id)
        sources.append(
            LearningSource(
                kind="page",
                source_id=page.id,
                source_ref=f"page:{page.id}",
                title=document.title,
                text=page.extracted_text,
                image_path=(
                    str(Path(request.app.state.data_dir, page.preview_path))
                    if include_page_images
                    else None
                ),
                page_number=page.page_number,
            )
        )
    for notebook_id in _load_ids(lesson.notebook_import_ids_json):
        notebook = session.get(NotebookImport, notebook_id)
        if notebook is None:
            raise NotFoundError("Notebook import", notebook_id)
        sources.append(
            LearningSource(
                kind="notebook",
                source_id=notebook.id,
                source_ref=f"notebook:{notebook.id}",
                title=notebook.title,
                text=notebook.raw_text,
            )
        )
    return LearningGenerationRequest(
        lesson_id=lesson.id,
        title=lesson.title,
        notes=lesson.notes,
        target_minutes=lesson.target_minutes,
        sources=tuple(sources),
        max_items=8,
    )


def _item_value(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, Mapping) else getattr(item, name)


def _generated_items(result: Any) -> list[Any]:
    if isinstance(result, Mapping):
        result = result.get("items", [])
    elif hasattr(result, "items") and not callable(result.items):
        result = result.items
    return list(result)[:8]


def _mark_generation_failed(
    session: Session, lesson: Lesson, error_code: str, now: datetime
) -> None:
    lesson.status = "generationFailed"
    lesson.generation_error = error_code
    lesson.updated_at = now
    session.add(lesson)
    session.commit()


@router.post("/lessons/{lesson_id}/generate")
async def generate_lesson(
    lesson_id: str, request: Request, session: SessionDependency
) -> dict[str, Any]:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise NotFoundError("Lesson", lesson_id)
    existing_questions = list(
        session.exec(select(Question).where(Question.lesson_id == lesson.id)).all()
    )
    if lesson.status == "ready" and len(existing_questions) >= 4:
        return _lesson_response(session, lesson)
    now = _now(request)
    factory: ProviderFactory | None = getattr(request.app.state, "ai_provider_factory", None)
    if factory is None:
        _mark_generation_failed(session, lesson, "AI_PROVIDER_UNAVAILABLE", now)
        raise ProviderUnavailableError()

    try:
        provider = factory()
        capabilities = provider.capabilities()
        vision_supported = _capability(capabilities, "vision")
        generation_request = _build_generation_request(
            lesson,
            request,
            session,
            include_page_images=vision_supported,
        )
        if any(
            source.kind == "page" and not source.text.strip()
            for source in generation_request.sources
        ) and not vision_supported:
            raise VisionUnsupportedError()
        generated = provider.generate_learning_items(generation_request)
        if inspect.isawaitable(generated):
            generated = await generated
        items = _generated_items(generated)
        if len(items) < 4:
            raise GenerationFailedError()
        allowed_source_refs = {source.source_ref for source in generation_request.sources}
        for item in items:
            source_refs = [str(ref) for ref in _item_value(item, "source_refs")]
            if not source_refs or not set(source_refs).issubset(allowed_source_refs):
                raise GenerationFailedError()

        for existing in session.exec(
            select(Question).where(Question.lesson_id == lesson.id)
        ).all():
            session.delete(existing)
        for existing in session.exec(
            select(KnowledgePoint).where(KnowledgePoint.lesson_id == lesson.id)
        ).all():
            session.delete(existing)

        for item in items:
            source_refs = [str(ref) for ref in _item_value(item, "source_refs")]
            point = KnowledgePoint(
                lesson_id=lesson.id,
                topic=str(_item_value(item, "topic")),
                explanation=str(_item_value(item, "explanation")),
                source_refs_json=json.dumps(source_refs, ensure_ascii=False),
                created_at=now,
            )
            session.add(point)
            session.flush()
            session.add(
                Question(
                    lesson_id=lesson.id,
                    knowledge_point_id=point.id,
                    prompt=str(_item_value(item, "question")),
                    reference_answer=str(_item_value(item, "reference_answer")),
                    explanation=str(_item_value(item, "explanation")),
                    source_refs_json=json.dumps(source_refs, ensure_ascii=False),
                    due_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        lesson.status = "ready"
        lesson.generation_error = None
        lesson.updated_at = now
        session.add(lesson)
        session.commit()
        session.refresh(lesson)
    except AppError as error:
        session.rollback()
        lesson = session.get(Lesson, lesson_id)
        if lesson is not None:
            _mark_generation_failed(session, lesson, error.code, now)
        raise
    except Exception as error:
        session.rollback()
        lesson = session.get(Lesson, lesson_id)
        if lesson is not None:
            _mark_generation_failed(session, lesson, "GENERATION_FAILED", now)
        raise GenerationFailedError() from error
    return _lesson_response(session, lesson)


@router.post("/review-sessions", status_code=status.HTTP_201_CREATED)
def create_review_session(
    payload: ReviewSessionCreate, request: Request, session: SessionDependency
) -> dict[str, Any]:
    now = _now(request)
    lesson = None
    if payload.lesson_id is None:
        selected = sorted(
            (
                question
                for question in session.exec(select(Question)).all()
                if not question.is_bad
                and question.schedule_status != "stable"
                and question.due_at is not None
                and _aware(question.due_at) <= now
            ),
            key=lambda question: _aware(question.due_at),
        )[:8]
    else:
        lesson = session.get(Lesson, payload.lesson_id)
        if lesson is None:
            raise NotFoundError("Lesson", payload.lesson_id)
        current = [
            question
            for question in session.exec(
                select(Question)
                .where(Question.lesson_id == lesson.id, Question.is_bad.is_(False))
                .order_by(Question.created_at)
            ).all()
            if question.schedule_status != "stable"
            and question.due_at is not None
            and _aware(question.due_at) <= now
        ]
        course_lesson_ids = [
            candidate.id
            for candidate in session.exec(
                select(Lesson).where(Lesson.course_id == lesson.course_id)
            ).all()
        ]
        course_questions = list(
            session.exec(select(Question).where(Question.lesson_id.in_(course_lesson_ids))).all()
        )
        current_ids = {question.id for question in current}
        due = sorted(
            (
                question
                for question in course_questions
                if question.id not in current_ids
                and not question.is_bad
                and question.schedule_status != "stable"
                and question.due_at is not None
                and _aware(question.due_at) <= now
            ),
            key=lambda question: _aware(question.due_at),
        )

        selected = current[:4]
        selected.extend(due[: 8 - len(selected)])
        if len(selected) < 8:
            selected_ids = {question.id for question in selected}
            selected.extend(
                question
                for question in current
                if question.id not in selected_ids
            )
        selected = selected[:8]
    review = ReviewSession(
        lesson_id=lesson.id if lesson is not None else None,
        question_ids_json=json.dumps([question.id for question in selected]),
        started_at=now,
        stop_adding_at=now + timedelta(minutes=12),
        hard_deadline_at=now + timedelta(minutes=15),
        status="active",
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    return _review_response(session, review)


@router.get("/review-sessions/{review_session_id}")
def get_review_session(
    review_session_id: str, session: SessionDependency
) -> dict[str, Any]:
    review = session.get(ReviewSession, review_session_id)
    if review is None:
        raise NotFoundError("Review session", review_session_id)
    return _review_response(session, review)


def _normalize_self_rating(value: str | None) -> str:
    ratings = {
        "certain": "certain",
        "confident": "certain",
        "sure": "certain",
        "fuzzy": "fuzzy",
        "unsure": "fuzzy",
        "uncertain": "fuzzy",
        "dontKnow": "dontKnow",
        "dont_know": "dontKnow",
        "unknown": "dontKnow",
    }
    if value not in ratings:
        raise InvalidSelfRatingError()
    return ratings[value]


def _answer_outcome(self_rating: str, verdict: str | None) -> str:
    if self_rating == "dontKnow" or verdict == "incorrect":
        return "notMastered"
    if self_rating == "fuzzy" or verdict == "partial":
        return "reinforce"
    if verdict == "unknown":
        return "mastered" if self_rating == "certain" else "reinforce"
    return "mastered"


@router.post(
    "/review-sessions/{review_session_id}/answers",
    status_code=status.HTTP_201_CREATED,
)
async def record_answer(
    review_session_id: str,
    payload: AnswerCreate,
    request: Request,
    session: SessionDependency,
) -> dict[str, Any]:
    review = session.get(ReviewSession, review_session_id)
    if review is None:
        raise NotFoundError("Review session", review_session_id)
    now = _now(request)
    if now > _aware(review.hard_deadline_at):
        raise ReviewSessionExpiredError()
    if payload.question_id not in _load_ids(review.question_ids_json):
        raise QuestionNotInSessionError()
    question = session.get(Question, payload.question_id)
    if question is None:
        raise NotFoundError("Question", payload.question_id)
    existing = session.exec(
        select(Attempt).where(
            Attempt.review_session_id == review.id,
            Attempt.question_id == question.id,
        )
    ).first()
    if existing is not None:
        raise AnswerAlreadyRecordedError()

    outcome: str | None = None
    self_rating: str | None = None
    assessment = payload.assessment
    if payload.action == "answered" and assessment is None:
        assessor = getattr(request.app.state, "ai_answer_assessor", None)
        if callable(assessor):
            assessor = assessor()
        if assessor is not None:
            try:
                generated_assessment = await asyncio.wait_for(
                    assessor.assess(
                        question.prompt,
                        question.reference_answer,
                        payload.answer_text,
                        _load_ids(question.source_refs_json),
                    ),
                    timeout=float(
                        getattr(request.app.state, "assessment_timeout_seconds", 5.0)
                    ),
                )
                assessment = AssessmentInput.model_validate(generated_assessment, from_attributes=True)
            except Exception:
                assessment = None
    verdict = assessment.verdict if assessment else None
    if payload.action == "bad":
        question.is_bad = True
        question.updated_at = now
    elif payload.action == "answered":
        self_rating = _normalize_self_rating(payload.self_rating)
        outcome = _answer_outcome(self_rating, verdict)
        schedule_outcome = {
            "mastered": ReviewOutcome.MASTERED,
            "reinforce": ReviewOutcome.SHAKY,
            "notMastered": ReviewOutcome.UNMASTERED,
        }[outcome]
        updated_schedule = schedule_next(
            stage=question.stage, outcome=schedule_outcome, now=now
        )
        question.stage = updated_schedule.stage
        question.due_at = updated_schedule.due_at
        question.schedule_status = updated_schedule.status
        question.mastery_state = outcome
        question.updated_at = now

    attempt = Attempt(
        review_session_id=review.id,
        question_id=question.id,
        action=payload.action,
        answer_text=payload.answer_text,
        self_rating=self_rating,
        assessment_verdict=verdict,
        missing_points_json=json.dumps(
            assessment.missing_points if assessment else [],
            ensure_ascii=False,
        ),
        feedback=assessment.feedback if assessment else "",
        outcome=outcome,
        created_at=now,
    )
    session.add(question)
    session.add(attempt)
    session.commit()
    session.refresh(question)
    session.refresh(attempt)
    attempted_ids = {
        item.question_id
        for item in session.exec(
            select(Attempt).where(Attempt.review_session_id == review.id)
        ).all()
    }
    if set(_load_ids(review.question_ids_json)).issubset(attempted_ids):
        review.status = "completed"
        session.add(review)
        session.commit()
    return {
        "id": attempt.id,
        "review_session_id": review.id,
        "question_id": question.id,
        "action": attempt.action,
        "selfRating": attempt.self_rating,
        "outcome": attempt.outcome,
        "feedback": attempt.feedback,
        "missing_points": _load_ids(attempt.missing_points_json),
        "question": _question_response(question),
    }


@router.patch("/questions/{question_id}")
def update_question(
    question_id: str,
    payload: QuestionPatch,
    request: Request,
    session: SessionDependency,
) -> dict[str, Any]:
    question = session.get(Question, question_id)
    if question is None:
        raise NotFoundError("Question", question_id)
    updates = payload.model_dump(exclude_unset=True)
    source_refs = updates.pop("source_refs", None)
    for field, value in updates.items():
        setattr(question, field, value)
    if source_refs is not None:
        question.source_refs_json = json.dumps(source_refs, ensure_ascii=False)
    question.updated_at = _now(request)
    session.add(question)
    session.commit()
    session.refresh(question)
    return _question_response(question)


@router.get("/dashboard")
def get_dashboard(
    request: Request, session: SessionDependency, course_id: str | None = None
) -> dict[str, Any]:
    now = _now(request)
    lessons = list(session.exec(select(Lesson)).all())
    if course_id is not None:
        lessons = [lesson for lesson in lessons if lesson.course_id == course_id]
    lesson_ids = {lesson.id for lesson in lessons}
    questions = [
        question
        for question in session.exec(select(Question)).all()
        if question.lesson_id in lesson_ids
    ]
    due = [
        question
        for question in questions
        if not question.is_bad
        and question.schedule_status != "stable"
        and question.due_at is not None
        and _aware(question.due_at) <= now
    ]
    today_lessons = [lesson for lesson in lessons if _aware(lesson.created_at).date() == now.date()]
    weak = [
        question
        for question in questions
        if not question.is_bad and question.mastery_state in {"reinforce", "notMastered"}
    ]
    return {
        "today_new_lessons": len(today_lessons),
        "due_count": len(due),
        "estimated_minutes": min(15, max(0, len(due) * 2)),
        "stable_count": sum(question.schedule_status == "stable" for question in questions),
        "reinforce_count": sum(question.mastery_state == "reinforce" for question in questions),
        "not_mastered_count": sum(
            question.mastery_state == "notMastered" for question in questions
        ),
        "weak_points": [
            {
                "question_id": question.id,
                "prompt": question.prompt,
                "mastery_state": question.mastery_state,
            }
            for question in weak[:5]
        ],
    }
