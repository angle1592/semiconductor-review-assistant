import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.content.models import Document, NotebookImport, Page
from app.courses.models import Course
from app.learning.models import Attempt, KnowledgePoint, Lesson, Question, ReviewSession
from app.main import create_app


def test_health_and_course_lifecycle(tmp_path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

        created = client.post(
            "/api/courses", json={"title": "晶圆制造基础", "description": "培训第一阶段"}
        )
        assert created.status_code == 201
        course = created.json()

        listed = client.get("/api/courses")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == course["id"]


def test_errors_use_consistent_problem_shape(tmp_path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/courses/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["request_id"]


def test_delete_course_removes_owned_data_and_keeps_other_course(tmp_path):
    app = create_app(data_dir=tmp_path)
    now = datetime.now(UTC)

    with Session(app.state.database) as session:
        deleted_course = Course(title="待删除课程")
        kept_course = Course(title="保留课程")
        session.add_all([deleted_course, kept_course])
        session.flush()

        deleted_document = Document(
            course_id=deleted_course.id,
            title="待删除课件",
            original_filename="delete.pdf",
            file_type="pdf",
            original_path="uploads/delete.pdf",
        )
        kept_document = Document(
            course_id=kept_course.id,
            title="保留课件",
            original_filename="keep.pdf",
            file_type="pdf",
            original_path="uploads/keep.pdf",
        )
        deleted_notebook = NotebookImport(
            course_id=deleted_course.id,
            title="待删除笔记",
            raw_text="delete",
        )
        kept_notebook = NotebookImport(
            course_id=kept_course.id,
            title="保留笔记",
            raw_text="keep",
        )
        session.add_all([deleted_document, kept_document, deleted_notebook, kept_notebook])
        session.flush()

        deleted_page = Page(
            document_id=deleted_document.id,
            page_number=1,
            preview_path=f"previews/{deleted_document.id}/1.png",
        )
        kept_page = Page(
            document_id=kept_document.id,
            page_number=1,
            preview_path=f"previews/{kept_document.id}/1.png",
        )
        session.add_all([deleted_page, kept_page])
        session.flush()

        deleted_lesson = Lesson(
            course_id=deleted_course.id,
            title="待删除课次",
            page_ids_json=json.dumps([deleted_page.id]),
            notebook_import_ids_json=json.dumps([deleted_notebook.id]),
        )
        kept_lesson = Lesson(
            course_id=kept_course.id,
            title="保留课次",
            page_ids_json=json.dumps([kept_page.id]),
            notebook_import_ids_json=json.dumps([kept_notebook.id]),
        )
        session.add_all([deleted_lesson, kept_lesson])
        session.flush()

        deleted_point = KnowledgePoint(lesson_id=deleted_lesson.id, topic="待删除知识点")
        kept_point = KnowledgePoint(lesson_id=kept_lesson.id, topic="保留知识点")
        session.add_all([deleted_point, kept_point])
        session.flush()
        deleted_question = Question(
            lesson_id=deleted_lesson.id,
            knowledge_point_id=deleted_point.id,
            prompt="待删除题目",
            reference_answer="待删除答案",
        )
        kept_question = Question(
            lesson_id=kept_lesson.id,
            knowledge_point_id=kept_point.id,
            prompt="保留题目",
            reference_answer="保留答案",
        )
        session.add_all([deleted_question, kept_question])
        session.flush()

        mixed_review = ReviewSession(
            lesson_id=deleted_lesson.id,
            question_ids_json=json.dumps([deleted_question.id, kept_question.id]),
            stop_adding_at=now + timedelta(minutes=12),
            hard_deadline_at=now + timedelta(minutes=15),
        )
        session.add(mixed_review)
        session.flush()
        deleted_attempt = Attempt(
            review_session_id=mixed_review.id,
            question_id=deleted_question.id,
            action="answered",
        )
        kept_attempt = Attempt(
            review_session_id=mixed_review.id,
            question_id=kept_question.id,
            action="answered",
        )
        session.add_all([deleted_attempt, kept_attempt])
        session.commit()

        ids = {
            "course": deleted_course.id,
            "kept_course": kept_course.id,
            "document": deleted_document.id,
            "kept_document": kept_document.id,
            "notebook": deleted_notebook.id,
            "kept_notebook": kept_notebook.id,
            "page": deleted_page.id,
            "kept_page": kept_page.id,
            "lesson": deleted_lesson.id,
            "kept_lesson": kept_lesson.id,
            "point": deleted_point.id,
            "kept_point": kept_point.id,
            "question": deleted_question.id,
            "kept_question": kept_question.id,
            "review": mixed_review.id,
            "deleted_attempt": deleted_attempt.id,
            "kept_attempt": kept_attempt.id,
        }

    for root in ("uploads", "processed", "previews"):
        document_dir = tmp_path / root / ids["document"]
        document_dir.mkdir(parents=True)
        (document_dir / "artifact.bin").write_bytes(b"delete")

    with TestClient(app) as client:
        response = client.delete(f"/api/courses/{ids['course']}")

    assert response.status_code == 204
    for root in ("uploads", "processed", "previews"):
        assert not (tmp_path / root / ids["document"]).exists()

    with Session(app.state.database) as session:
        for model, key in (
            (Course, "course"),
            (Document, "document"),
            (NotebookImport, "notebook"),
            (Page, "page"),
            (Lesson, "lesson"),
            (KnowledgePoint, "point"),
            (Question, "question"),
            (Attempt, "deleted_attempt"),
        ):
            assert session.get(model, ids[key]) is None

        for model, key in (
            (Course, "kept_course"),
            (Document, "kept_document"),
            (NotebookImport, "kept_notebook"),
            (Page, "kept_page"),
            (Lesson, "kept_lesson"),
            (KnowledgePoint, "kept_point"),
            (Question, "kept_question"),
            (Attempt, "kept_attempt"),
        ):
            assert session.get(model, ids[key]) is not None

        review = session.get(ReviewSession, ids["review"])
        assert review is not None
        assert review.lesson_id is None
        assert json.loads(review.question_ids_json) == [ids["kept_question"]]


def test_delete_missing_course_uses_consistent_not_found_error(tmp_path):
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        response = client.delete("/api/courses/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
