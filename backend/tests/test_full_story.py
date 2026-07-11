from io import BytesIO
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.ai.schemas import GeneratedLearningItem, GeneratedLearningItems, ProviderCapabilities
from app.main import create_app


class StoryProvider:
    def capabilities(self):
        return ProviderCapabilities(text=True, vision=True, structured_output=True)

    async def generate_learning_items(self, request):
        return GeneratedLearningItems(
            items=[
                GeneratedLearningItem(
                    topic=f"光刻 {index + 1}",
                    question=f"光刻把什么转移到哪里？（{index + 1}）",
                    reference_answer="把掩膜图形转移到晶圆表面的光刻胶。",
                    explanation="这是后续选择性刻蚀或注入的图形基础。",
                    source_refs=[request.sources[0].source_ref],
                )
                for index in range(4)
            ]
        )


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Lithography transfers a mask pattern to photoresist.")
    content = document.tobytes()
    document.close()
    return content


def test_complete_after_class_review_story(tmp_path: Path):
    app = create_app(data_dir=tmp_path, learning_provider_factory=lambda: StoryProvider())
    with TestClient(app) as client:
        course = client.post("/api/courses", json={"title": "晶圆制造"}).json()
        document = client.post(
            f"/api/courses/{course['id']}/documents",
            files={"file": ("lesson.pdf", BytesIO(_pdf_bytes()), "application/pdf")},
        ).json()
        lesson = client.post(
            "/api/lessons",
            json={
                "course_id": course["id"],
                "title": "光刻课后复习",
                "notes": "老师强调图形转移",
                "page_ids": [document["pages"][0]["id"]],
            },
        ).json()
        generated = client.post(f"/api/lessons/{lesson['id']}/generate").json()
        review = client.post("/api/review-sessions", json={"lesson_id": lesson["id"]}).json()
        answer = client.post(
            f"/api/review-sessions/{review['id']}/answers",
            json={
                "question_id": review["questions"][0]["id"],
                "action": "answered",
                "answer_text": "掩膜图形转移到光刻胶",
                "selfRating": "certain",
                "assessment": {"verdict": "correct", "missing_points": [], "feedback": "完整"},
            },
        )
        dashboard = client.get("/api/dashboard").json()
        backup = client.get("/api/backups/export")

    assert generated["status"] == "ready"
    assert generated["questions"][0]["source_refs"][0].startswith("page:")
    assert "reference_answer" not in review["questions"][0]
    assert answer.status_code == 201
    assert answer.json()["outcome"] == "mastered"
    assert answer.json()["question"]["stage"] == 1
    assert dashboard["stable_count"] == 0
    assert dashboard["reinforce_count"] == 0
    assert dashboard["not_mastered_count"] == 0
    assert backup.status_code == 200
