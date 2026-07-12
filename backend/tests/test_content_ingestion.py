import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.learning.models import Attempt, KnowledgePoint, Lesson, Question, ReviewSession
from app.main import create_app


def _create_course(client: TestClient) -> str:
    response = client.post("/api/courses", json={"title": "半导体器件", "description": ""})
    assert response.status_code == 201
    return response.json()["id"]


def _two_page_pdf() -> bytes:
    document = fitz.open()
    for text in ("MOSFET threshold voltage", "Thermal oxide growth"):
        page = document.new_page(width=400, height=300)
        page.insert_text((40, 80), text, fontsize=16)
    payload = document.tobytes()
    document.close()
    return payload


def _image_only_pdf() -> bytes:
    source = fitz.open()
    source_page = source.new_page(width=320, height=180)
    source_page.draw_rect(
        fitz.Rect(20, 20, 300, 160),
        color=(0.1, 0.25, 0.55),
        fill=(0.85, 0.9, 0.98),
        width=2,
    )
    source_page.draw_circle(
        fitz.Point(160, 90),
        46,
        color=(0.85, 0.3, 0.12),
        fill=(0.98, 0.72, 0.45),
    )
    raster = source_page.get_pixmap(alpha=False).tobytes("png")
    source.close()

    document = fitz.open()
    page = document.new_page(width=320, height=180)
    page.insert_image(page.rect, stream=raster)
    payload = document.tobytes()
    document.close()
    return payload


def test_pdf_upload_extracts_numbered_pages_and_serves_png_previews(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    pdf_payload = _two_page_pdf()

    with TestClient(app) as client:
        course_id = _create_course(client)
        uploaded = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("week-01.pdf", pdf_payload, "application/pdf")},
        )

        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]
        fetched = client.get(f"/api/documents/{document_id}")

        assert fetched.status_code == 200
        body = fetched.json()
        assert body["course_id"] == course_id
        assert body["original_filename"] == "week-01.pdf"
        assert body["file_type"] == "pdf"
        assert body["page_count"] == 2
        assert [page["page_number"] for page in body["pages"]] == [1, 2]
        assert "MOSFET threshold voltage" in body["pages"][0]["extracted_text"]
        assert body["pages"][0]["source"]["document_id"] == document_id
        assert body["pages"][0]["source"]["filename"] == "week-01.pdf"
        assert body["pages"][0]["source"]["page_number"] == 1

        preview = client.get(body["pages"][0]["preview_url"])
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")

    originals = list((tmp_path / "uploads").rglob("week-01.pdf"))
    assert len(originals) == 1
    assert originals[0].read_bytes() == pdf_payload


def test_delete_document_cascades_learning_data_without_harming_other_sources(
    tmp_path: Path,
) -> None:
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        affected_document = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("temporary.pdf", _two_page_pdf(), "application/pdf")},
        ).json()
        other_document = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("keep.pdf", _two_page_pdf(), "application/pdf")},
        ).json()
        document_id = affected_document["id"]
        page_id = affected_document["pages"][0]["id"]
        preview_url = affected_document["pages"][0]["preview_url"]
        affected_lesson = client.post(
            "/api/lessons",
            json={
                "course_id": course_id,
                "title": "测试课次",
                "notes": "",
                "target_minutes": 10,
                "page_ids": [page_id],
                "notebook_import_ids": [],
            },
        ).json()
        other_lesson = client.post(
            "/api/lessons",
            json={
                "course_id": course_id,
                "title": "保留课次",
                "notes": "",
                "target_minutes": 10,
                "page_ids": [other_document["pages"][0]["id"]],
                "notebook_import_ids": [],
            },
        ).json()
        now = datetime.now(UTC)
        with Session(app.state.database) as session:
            affected_point = KnowledgePoint(
                lesson_id=affected_lesson["id"],
                topic="待删除知识点",
                source_refs_json=json.dumps([f"page:{page_id}"]),
            )
            other_point = KnowledgePoint(
                lesson_id=other_lesson["id"],
                topic="保留知识点",
                source_refs_json=json.dumps([f"page:{other_document['pages'][0]['id']}"]),
            )
            session.add(affected_point)
            session.add(other_point)
            session.flush()
            affected_question = Question(
                lesson_id=affected_lesson["id"],
                knowledge_point_id=affected_point.id,
                prompt="待删除题目",
                reference_answer="待删除答案",
                source_refs_json=json.dumps([f"page:{page_id}"]),
            )
            other_question = Question(
                lesson_id=other_lesson["id"],
                knowledge_point_id=other_point.id,
                prompt="保留题目",
                reference_answer="保留答案",
                source_refs_json=json.dumps([f"page:{other_document['pages'][0]['id']}"]),
            )
            session.add(affected_question)
            session.add(other_question)
            session.flush()
            mixed_review = ReviewSession(
                lesson_id=affected_lesson["id"],
                question_ids_json=json.dumps([affected_question.id, other_question.id]),
                stop_adding_at=now + timedelta(minutes=12),
                hard_deadline_at=now + timedelta(minutes=15),
            )
            affected_only_review = ReviewSession(
                lesson_id=affected_lesson["id"],
                question_ids_json=json.dumps([affected_question.id]),
                stop_adding_at=now + timedelta(minutes=12),
                hard_deadline_at=now + timedelta(minutes=15),
            )
            unrelated_empty_review = ReviewSession(
                lesson_id=other_lesson["id"],
                question_ids_json="[]",
                stop_adding_at=now + timedelta(minutes=12),
                hard_deadline_at=now + timedelta(minutes=15),
            )
            session.add(mixed_review)
            session.add(affected_only_review)
            session.add(unrelated_empty_review)
            session.flush()
            affected_attempt = Attempt(
                review_session_id=mixed_review.id,
                question_id=affected_question.id,
                action="answered",
                answer_text="错误测试答案",
            )
            other_attempt = Attempt(
                review_session_id=mixed_review.id,
                question_id=other_question.id,
                action="answered",
                answer_text="应保留答案",
            )
            affected_only_attempt = Attempt(
                review_session_id=affected_only_review.id,
                question_id=affected_question.id,
                action="answered",
                answer_text="待删除答案",
            )
            session.add(affected_attempt)
            session.add(other_attempt)
            session.add(affected_only_attempt)
            session.commit()
            affected_point_id = affected_point.id
            other_point_id = other_point.id
            affected_question_id = affected_question.id
            other_question_id = other_question.id
            mixed_review_id = mixed_review.id
            affected_only_review_id = affected_only_review.id
            unrelated_empty_review_id = unrelated_empty_review.id
            affected_attempt_id = affected_attempt.id
            other_attempt_id = other_attempt.id
            affected_only_attempt_id = affected_only_attempt.id
        processed = tmp_path / "processed" / document_id / "converted.pdf"
        processed.parent.mkdir(parents=True)
        processed.write_bytes(b"converted")

        deleted = client.delete(f"/api/documents/{document_id}")

        assert deleted.status_code == 204
        assert client.get(f"/api/documents/{document_id}").status_code == 404
        assert client.get(preview_url).status_code == 404
        assert client.get(f"/api/lessons/{affected_lesson['id']}").status_code == 404
        assert client.get(f"/api/lessons/{other_lesson['id']}").status_code == 200
        assert client.get(f"/api/documents/{other_document['id']}").status_code == 200

        with Session(app.state.database) as session:
            assert session.get(Lesson, affected_lesson["id"]) is None
            assert session.get(KnowledgePoint, affected_point_id) is None
            assert session.get(Question, affected_question_id) is None
            assert session.get(Attempt, affected_attempt_id) is None
            assert session.get(Attempt, affected_only_attempt_id) is None
            assert session.get(ReviewSession, affected_only_review_id) is None

            assert session.get(Lesson, other_lesson["id"]) is not None
            assert session.get(KnowledgePoint, other_point_id) is not None
            assert session.get(Question, other_question_id) is not None
            assert session.get(Attempt, other_attempt_id) is not None
            assert session.get(ReviewSession, unrelated_empty_review_id) is not None
            mixed = session.get(ReviewSession, mixed_review_id)
            assert mixed is not None
            assert mixed.lesson_id is None
            assert json.loads(mixed.question_ids_json) == [other_question_id]

    assert not (tmp_path / "uploads" / document_id).exists()
    assert not (tmp_path / "processed" / document_id).exists()
    assert not (tmp_path / "previews" / document_id).exists()


def test_image_only_pdf_upload_keeps_page_mapping_without_inventing_text(
    tmp_path: Path,
) -> None:
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        uploaded = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("wafer-map.pdf", _image_only_pdf(), "application/pdf")},
        )

        assert uploaded.status_code == 201
        body = uploaded.json()
        assert body["page_count"] == 1
        assert body["pages"][0]["page_number"] == 1
        assert body["pages"][0]["extracted_text"] == ""
        assert body["pages"][0]["source"] == {
            "document_id": body["id"],
            "filename": "wafer-map.pdf",
            "page_number": 1,
        }

        preview = client.get(body["pages"][0]["preview_url"])

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_notebook_import_preserves_full_raw_text_and_source(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    raw_text = "# PN 结复习\n\n- 空穴扩散\n\n```text\n  保留缩进  \n```\n"

    with TestClient(app) as client:
        course_id = _create_course(client)
        response = client.post(
            f"/api/courses/{course_id}/notebook-imports",
            json={
                "title": "NotebookLM 学习指南",
                "raw_text": raw_text,
                "source_filename": "guide.md",
            },
        )

    assert response.status_code == 201
    assert response.json()["course_id"] == course_id
    assert response.json()["raw_text"] == raw_text
    assert response.json()["source_filename"] == "guide.md"


def test_document_upload_rejects_unknown_extension_and_empty_file(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        unsupported = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("notes.txt", b"content", "text/plain")},
        )
        empty = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        invalid = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("broken.pdf", b"not-a-pdf", "application/pdf")},
        )

    assert unsupported.status_code == 422
    assert unsupported.json()["code"] == "UNSUPPORTED_DOCUMENT_TYPE"
    assert empty.status_code == 422
    assert empty.json()["code"] == "EMPTY_DOCUMENT"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_DOCUMENT"
    assert not any(path.is_file() for path in (tmp_path / "uploads").rglob("*"))
    assert not any(path.is_file() for path in (tmp_path / "previews").rglob("*"))


def test_powerpoint_unavailable_is_typed_and_cleans_partial_files(
    tmp_path: Path, monkeypatch
) -> None:
    from app.content import service
    from app.content.errors import PowerPointUnavailableError

    def unavailable(_source_path: Path, _target_path: Path) -> None:
        raise PowerPointUnavailableError()

    monkeypatch.setattr(service, "export_powerpoint_to_pdf", unavailable)
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        response = client.post(
            f"/api/courses/{course_id}/documents",
            files={
                "file": (
                    "lecture.pptx",
                    b"not-a-real-presentation",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            },
        )

    assert response.status_code == 503
    assert response.json()["code"] == "POWERPOINT_UNAVAILABLE"
    assert not list((tmp_path / "uploads").rglob("lecture.pptx"))
    assert not any(path.is_file() for path in (tmp_path / "processed").rglob("*"))
    assert not any(path.is_file() for path in (tmp_path / "previews").rglob("*"))


@pytest.mark.parametrize(
    ("filename", "content_type", "expected_type"),
    [
        ("lecture.ppt", "application/vnd.ms-powerpoint", "ppt"),
        (
            "lecture.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
        ),
    ],
)
def test_powerpoint_successfully_enters_the_pdf_page_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    expected_type: str,
) -> None:
    from app.content import service

    converted_pdf = _two_page_pdf()
    conversion_calls: list[tuple[Path, Path]] = []

    def export_as_pdf(source_path: Path, target_path: Path) -> None:
        conversion_calls.append((source_path, target_path))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(converted_pdf)

    monkeypatch.setattr(service, "export_powerpoint_to_pdf", export_as_pdf)
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        uploaded = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": (filename, b"presentation-source", content_type)},
        )

        assert uploaded.status_code == 201
        body = uploaded.json()
        assert body["file_type"] == expected_type
        assert body["original_filename"] == filename
        assert body["page_count"] == 2
        assert [page["page_number"] for page in body["pages"]] == [1, 2]
        assert "MOSFET threshold voltage" in body["pages"][0]["extracted_text"]
        assert "Thermal oxide growth" in body["pages"][1]["extracted_text"]
        assert all(page["source"]["filename"] == filename for page in body["pages"])

        first_preview = client.get(body["pages"][0]["preview_url"])

    assert first_preview.status_code == 200
    assert first_preview.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(conversion_calls) == 1
    source_path, target_path = conversion_calls[0]
    assert source_path.name == filename
    assert source_path.read_bytes() == b"presentation-source"
    assert target_path.name == "converted.pdf"
    assert target_path.read_bytes() == converted_pdf
