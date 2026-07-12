import json

from sqlmodel import Session, select

from app.learning.models import Attempt, KnowledgePoint, Lesson, Question, ReviewSession


def _load_ids(value: str) -> list[str]:
    return [str(item) for item in json.loads(value)]


def cascade_document_learning_data(session: Session, page_ids: list[str]) -> None:
    affected_pages = set(page_ids)
    lessons = list(session.exec(select(Lesson)).all())
    affected_lessons = [
        lesson for lesson in lessons if affected_pages.intersection(_load_ids(lesson.page_ids_json))
    ]
    if not affected_lessons:
        return

    lesson_ids = {lesson.id for lesson in affected_lessons}
    questions = list(session.exec(select(Question).where(Question.lesson_id.in_(lesson_ids))).all())
    question_ids = {question.id for question in questions}
    knowledge_points = list(
        session.exec(select(KnowledgePoint).where(KnowledgePoint.lesson_id.in_(lesson_ids))).all()
    )

    attempts_to_delete: dict[str, Attempt] = {}
    if question_ids:
        for attempt in session.exec(
            select(Attempt).where(Attempt.question_id.in_(question_ids))
        ).all():
            attempts_to_delete[attempt.id] = attempt

    reviews_to_delete: list[ReviewSession] = []
    for review in session.exec(select(ReviewSession)).all():
        original_question_ids = _load_ids(review.question_ids_json)
        removes_question = bool(question_ids.intersection(original_question_ids))
        if review.lesson_id not in lesson_ids and not removes_question:
            continue
        remaining_question_ids = [
            question_id for question_id in original_question_ids if question_id not in question_ids
        ]
        if not remaining_question_ids:
            reviews_to_delete.append(review)
            for attempt in session.exec(
                select(Attempt).where(Attempt.review_session_id == review.id)
            ).all():
                attempts_to_delete[attempt.id] = attempt
            continue
        if review.lesson_id in lesson_ids:
            review.lesson_id = None
        if remaining_question_ids != original_question_ids:
            review.question_ids_json = json.dumps(remaining_question_ids)
        session.add(review)

    for attempt in attempts_to_delete.values():
        session.delete(attempt)
    for review in reviews_to_delete:
        session.delete(review)
    for question in questions:
        session.delete(question)
    for point in knowledge_points:
        session.delete(point)
    for lesson in affected_lessons:
        session.delete(lesson)
