import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.content.models import Document, NotebookImport, Page
from app.courses.models import Course
from app.learning.models import Lesson, Question
from app.learning.provider import LearningGenerationRequest
from app.learning.router import router
from app.shared.database import create_database
from app.shared.errors import AppError, app_error_handler
from app.shared.request_id import RequestIdMiddleware


NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


class FakeProvider:
    def __init__(
        self,
        *,
        vision: bool = True,
        item_count: int = 6,
        source_ref_override: str | None = None,
    ):
        self.vision = vision
        self.item_count = item_count
        self.source_ref_override = source_ref_override
        self.requests: list[LearningGenerationRequest] = []

    def capabilities(self):
        return {"text": True, "vision": self.vision, "structured_output": True}

    def generate_learning_items(self, request: LearningGenerationRequest):
        self.requests.append(request)
        source_ref = self.source_ref_override or request.sources[0].source_ref
        return [
            {
                "topic": f"知识点 {index + 1}",
                "question": f"问题 {index + 1}",
                "reference_answer": f"答案 {index + 1}",
                "explanation": "简短解释",
                "source_refs": [source_ref],
            }
            for index in range(self.item_count)
        ]


def _create_test_app(tmp_path: Path, provider: FakeProvider) -> FastAPI:
    app = FastAPI()
    app.state.data_dir = tmp_path
    app.state.ai_provider_factory = lambda: provider
    app.state.now_provider = lambda: NOW
    app.state.database = create_database(tmp_path)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(router)
    return app


def _seed_sources(app: FastAPI) -> dict[str, str]:
    with Session(app.state.database) as session:
        course = Course(title="器件物理", description="")
        session.add(course)
        session.commit()
        session.refresh(course)

        document = Document(
            course_id=course.id,
            title="第一讲",
            original_filename="lesson.pdf",
            file_type="pdf",
            original_path="uploads/lesson.pdf",
            page_count=2,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        selected_page = Page(
            document_id=document.id,
            page_number=1,
            extracted_text="selected MOSFET text",
            preview_path="previews/selected.png",
        )
        unselected_page = Page(
            document_id=document.id,
            page_number=2,
            extracted_text="SECRET UNSELECTED PAGE",
            preview_path="previews/unselected.png",
        )
        notebook = NotebookImport(
            course_id=course.id,
            title="学习指南",
            raw_text="selected notebook text",
            source_filename="guide.md",
        )
        session.add_all([selected_page, unselected_page, notebook])
        session.commit()
        session.refresh(selected_page)
        session.refresh(unselected_page)
        session.refresh(notebook)
        return {
            "course_id": course.id,
            "document_id": document.id,
            "page_id": selected_page.id,
            "unselected_page_id": unselected_page.id,
            "notebook_id": notebook.id,
        }


def _create_lesson(client: TestClient, source_ids: dict[str, str]) -> dict:
    response = client.post(
        "/api/lessons",
        json={
            "course_id": source_ids["course_id"],
            "title": "MOSFET 阈值电压",
            "notes": "老师强调体效应",
            "target_minutes": 10,
            "page_ids": [source_ids["page_id"]],
            "notebook_import_ids": [source_ids["notebook_id"]],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_lesson_creation_validates_sources_and_target_then_reads_draft(tmp_path: Path):
    app = _create_test_app(tmp_path, FakeProvider())
    source_ids = _seed_sources(app)

    with TestClient(app) as client:
        lesson = _create_lesson(client, source_ids)
        fetched = client.get(f"/api/lessons/{lesson['id']}")
        missing = client.post(
            "/api/lessons",
            json={
                "course_id": source_ids["course_id"],
                "title": "无效来源",
                "notes": "",
                "target_minutes": 10,
                "page_ids": ["missing"],
                "notebook_import_ids": [],
            },
        )
        too_long = client.post(
            "/api/lessons",
            json={
                "course_id": source_ids["course_id"],
                "title": "时间过长",
                "notes": "",
                "target_minutes": 16,
                "page_ids": [source_ids["page_id"]],
                "notebook_import_ids": [],
            },
        )

    assert lesson["status"] == "draft"
    assert lesson["target_minutes"] == 10
    assert fetched.status_code == 200
    assert fetched.json()["page_ids"] == [source_ids["page_id"]]
    assert missing.status_code == 404
    assert too_long.status_code == 422


def test_generation_sends_only_selected_sources_caps_at_eight_and_marks_ready(tmp_path: Path):
    provider = FakeProvider(item_count=10)
    app = _create_test_app(tmp_path, provider)
    source_ids = _seed_sources(app)

    with TestClient(app) as client:
        lesson = _create_lesson(client, source_ids)
        response = client.post(f"/api/lessons/{lesson['id']}/generate")
        repeated = client.post(f"/api/lessons/{lesson['id']}/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["questions"]) == 8
    assert [item["id"] for item in repeated.json()["questions"]] == [
        item["id"] for item in body["questions"]
    ]
    assert len(provider.requests) == 1
    assert all(question["source_refs"] for question in body["questions"])
    request = provider.requests[0]
    assert request.max_items == 8
    assert {source.source_id for source in request.sources} == {
        source_ids["page_id"],
        source_ids["notebook_id"],
    }
    assert "SECRET UNSELECTED PAGE" not in " ".join(source.text for source in request.sources)
    page_source = next(source for source in request.sources if source.kind == "page")
    assert Path(page_source.image_path).parts[-2:] == ("previews", "selected.png")


def test_generation_without_vision_marks_page_lesson_failed(tmp_path: Path):
    provider = FakeProvider(vision=False)
    app = _create_test_app(tmp_path, provider)
    source_ids = _seed_sources(app)
    with Session(app.state.database) as session:
        page = session.get(Page, source_ids["page_id"])
        assert page is not None
        page.extracted_text = ""
        session.add(page)
        session.commit()

    with TestClient(app) as client:
        lesson = _create_lesson(client, source_ids)
        response = client.post(f"/api/lessons/{lesson['id']}/generate")
        fetched = client.get(f"/api/lessons/{lesson['id']}")

    assert response.status_code == 422
    assert response.json()["code"] == "VISION_UNSUPPORTED"
    assert fetched.json()["status"] == "generationFailed"
    assert provider.requests == []


def test_generation_without_vision_uses_a_text_pdf_without_sending_its_preview(
    tmp_path: Path,
):
    provider = FakeProvider(vision=False)
    app = _create_test_app(tmp_path, provider)
    source_ids = _seed_sources(app)

    with TestClient(app) as client:
        lesson = _create_lesson(client, source_ids)
        response = client.post(f"/api/lessons/{lesson['id']}/generate")

    assert response.status_code == 200
    page_source = next(
        source for source in provider.requests[0].sources if source.kind == "page"
    )
    assert page_source.text == "selected MOSFET text"
    assert page_source.image_path is None


def test_generation_rejects_too_few_items_and_unselected_source_refs(tmp_path: Path):
    for provider in (
        FakeProvider(item_count=3),
        FakeProvider(source_ref_override="page:not-selected"),
    ):
        case_dir = tmp_path / str(len(provider.requests)) / str(id(provider))
        app = _create_test_app(case_dir, provider)
        source_ids = _seed_sources(app)

        with TestClient(app) as client:
            lesson = _create_lesson(client, source_ids)
            response = client.post(f"/api/lessons/{lesson['id']}/generate")
            fetched = client.get(f"/api/lessons/{lesson['id']}").json()

        assert response.status_code == 502
        assert response.json()["code"] == "GENERATION_FAILED"
        assert fetched["status"] == "generationFailed"
        assert fetched["questions"] == []


def _seed_review_questions(app: FastAPI, source_ids: dict[str, str]) -> str:
    with Session(app.state.database) as session:
        current = Lesson(
            course_id=source_ids["course_id"],
            title="今天的新课",
            notes="",
            target_minutes=10,
            page_ids_json=json.dumps([source_ids["page_id"]]),
            notebook_import_ids_json="[]",
            status="ready",
            created_at=NOW,
            updated_at=NOW,
        )
        old = Lesson(
            course_id=source_ids["course_id"],
            title="旧课",
            notes="",
            target_minutes=10,
            page_ids_json=json.dumps([source_ids["page_id"]]),
            notebook_import_ids_json="[]",
            status="ready",
            created_at=NOW - timedelta(days=10),
            updated_at=NOW - timedelta(days=10),
        )
        session.add_all([current, old])
        session.commit()
        session.refresh(current)
        session.refresh(old)
        for index in range(6):
            session.add(
                Question(
                    lesson_id=current.id,
                    prompt=f"当天题 {index}",
                    reference_answer="不应出现在会话读取中",
                    explanation="隐藏解释",
                    source_refs_json=json.dumps([f"page:{source_ids['page_id']}"]),
                    due_at=NOW,
                )
            )
        for index in range(5):
            session.add(
                Question(
                    lesson_id=old.id,
                    prompt=f"到期题 {index}",
                    reference_answer="旧答案",
                    explanation="旧解释",
                    source_refs_json=json.dumps([f"page:{source_ids['page_id']}"]),
                    due_at=NOW - timedelta(days=1),
                    is_bad=index == 4,
                )
            )
        session.commit()
        return current.id


def test_review_session_prioritizes_four_current_then_due_and_hides_answers(tmp_path: Path):
    app = _create_test_app(tmp_path, FakeProvider())
    source_ids = _seed_sources(app)
    lesson_id = _seed_review_questions(app, source_ids)

    with TestClient(app) as client:
        created = client.post("/api/review-sessions", json={"lesson_id": lesson_id})
        fetched = client.get(f"/api/review-sessions/{created.json()['id']}")

    assert created.status_code == 201
    body = fetched.json()
    assert len(body["questions"]) == 8
    assert sum(question["lesson_id"] == lesson_id for question in body["questions"]) >= 4
    assert all("reference_answer" not in question for question in body["questions"])
    assert all("explanation" not in question for question in body["questions"])
    assert body["questions"][0]["sources"] == [
        {
            "kind": "page",
            "source_ref": f"page:{source_ids['page_id']}",
            "document_id": source_ids["document_id"],
            "page_id": source_ids["page_id"],
            "filename": "lesson.pdf",
            "page_number": 1,
            "preview_url": f"/api/pages/{source_ids['page_id']}/preview",
        }
    ]
    assert datetime.fromisoformat(body["stop_adding_at"]) == NOW + timedelta(minutes=12)
    assert datetime.fromisoformat(body["hard_deadline_at"]) == NOW + timedelta(minutes=15)


def test_due_review_can_start_without_a_current_lesson(tmp_path: Path):
    app = _create_test_app(tmp_path, FakeProvider())
    source_ids = _seed_sources(app)
    _seed_review_questions(app, source_ids)

    with TestClient(app) as client:
        created = client.post("/api/review-sessions", json={})

    assert created.status_code == 201
    body = created.json()
    assert body["lesson_id"] is None
    assert 1 <= len(body["questions"]) <= 8
    assert all(question["is_bad"] is False for question in body["questions"])


def test_answers_apply_schedule_while_skipped_and_bad_do_not_and_question_can_be_fixed(
    tmp_path: Path,
):
    app = _create_test_app(tmp_path, FakeProvider())
    source_ids = _seed_sources(app)
    lesson_id = _seed_review_questions(app, source_ids)

    with TestClient(app) as client:
        review = client.post("/api/review-sessions", json={"lesson_id": lesson_id}).json()
        first, second, third, fourth = [question["id"] for question in review["questions"][:4]]

        mastered = client.post(
            f"/api/review-sessions/{review['id']}/answers",
            json={
                "question_id": first,
                "action": "answered",
                "answer_text": "我的回答",
                "selfRating": "certain",
                "assessment": {
                    "verdict": "correct",
                    "missing_points": [],
                    "feedback": "正确",
                },
            },
        )
        offline = client.post(
            f"/api/review-sessions/{review['id']}/answers",
            json={
                "question_id": second,
                "action": "answered",
                "answer_text": "不太确定",
                "selfRating": "fuzzy",
            },
        )
        skipped = client.post(
            f"/api/review-sessions/{review['id']}/answers",
            json={"question_id": third, "action": "skipped"},
        )
        bad = client.post(
            f"/api/review-sessions/{review['id']}/answers",
            json={"question_id": fourth, "action": "bad"},
        )
        fixed = client.patch(
            f"/api/questions/{fourth}",
            json={
                "prompt": "修正后的题目",
                "reference_answer": "修正后的答案",
                "is_bad": False,
            },
        )
        reopened = client.post("/api/review-sessions", json={"lesson_id": lesson_id})

    assert mastered.status_code == 201
    assert mastered.json()["outcome"] == "mastered"
    assert mastered.json()["question"]["stage"] == 1
    assert datetime.fromisoformat(mastered.json()["question"]["due_at"]) == NOW + timedelta(
        days=2
    )
    assert offline.json()["outcome"] == "reinforce"
    assert offline.json()["question"]["stage"] == 0
    assert datetime.fromisoformat(offline.json()["question"]["due_at"]) == NOW + timedelta(
        days=1
    )
    assert skipped.json()["outcome"] is None
    assert bad.json()["question"]["is_bad"] is True
    assert fixed.json()["prompt"] == "修正后的题目"
    assert fixed.json()["reference_answer"] == "修正后的答案"
    assert fixed.json()["is_bad"] is False
    assert first not in {question["id"] for question in reopened.json()["questions"]}


def test_ai_assessment_timeout_falls_back_to_self_rating_quickly(tmp_path: Path):
    class SlowAssessor:
        async def assess(self, *_args):
            await asyncio.sleep(1)

    app = _create_test_app(tmp_path, FakeProvider())
    app.state.ai_answer_assessor = SlowAssessor()
    app.state.assessment_timeout_seconds = 0.01
    source_ids = _seed_sources(app)
    lesson_id = _seed_review_questions(app, source_ids)

    with TestClient(app) as client:
        review = client.post("/api/review-sessions", json={"lesson_id": lesson_id}).json()
        started = time.perf_counter()
        response = client.post(
            f"/api/review-sessions/{review['id']}/answers",
            json={
                "question_id": review["questions"][0]["id"],
                "action": "answered",
                "answer_text": "不确定",
                "selfRating": "fuzzy",
            },
        )
        elapsed = time.perf_counter() - started

    assert response.status_code == 201
    assert response.json()["outcome"] == "reinforce"
    assert elapsed < 0.5
