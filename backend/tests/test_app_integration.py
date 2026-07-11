from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.ai.schemas import GeneratedLearningItem, GeneratedLearningItems, ProviderCapabilities
from app.main import create_app


class FakeLearningProvider:
    def capabilities(self):
        return ProviderCapabilities(text=True, vision=True, structured_output=True)

    async def generate_learning_items(self, request):
        source = request.sources[0]
        return GeneratedLearningItems(
            items=[
                GeneratedLearningItem(
                    topic="薄膜沉积",
                    question="这页课件的核心工艺目的是什么？",
                    reference_answer="形成满足要求的薄膜。",
                    explanation="关注膜厚和均匀性。",
                    source_refs=[source.source_ref],
                )
            ]
        )


def test_main_app_registers_learning_routes_and_document_listing(tmp_path: Path):
    app = create_app(
        data_dir=tmp_path,
        learning_provider_factory=lambda: FakeLearningProvider(),
    )
    with TestClient(app) as client:
        course = client.post("/api/courses", json={"title": "工艺基础"}).json()
        response = client.get(f"/api/courses/{course['id']}/documents")
        assert response.status_code == 200
        assert response.json() == []
        assert client.post("/api/lessons", json={"course_id": course["id"], "title": "空"}).status_code == 422


def test_backup_export_validate_and_restore_excludes_secrets(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        client.post("/api/courses", json={"title": "可靠性"})
        exported = client.get("/api/backups/export")
        assert exported.status_code == 200
        archive = exported.content

        with ZipFile(BytesIO(archive)) as bundle:
            names = bundle.namelist()
            assert "manifest.json" in names
            assert not any("api_key" in name.lower() or "secret" in name.lower() for name in names)

        validated = client.post(
            "/api/backups/validate",
            files={"file": ("backup.zip", archive, "application/zip")},
        )
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        assert validated.json()["manifest"]["contains_secrets"] is False

        tampered_stream = BytesIO(archive)
        with ZipFile(tampered_stream, "a") as bundle:
            bundle.writestr("data/unlisted.txt", b"not in manifest")
        tampered = client.post(
            "/api/backups/validate",
            files={"file": ("tampered.zip", tampered_stream.getvalue(), "application/zip")},
        )
        assert tampered.status_code == 200
        assert tampered.json()["valid"] is False

        stale = tmp_path / "uploads" / "stale" / "old.bin"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"created after backup")

        restored = client.post(
            "/api/backups/restore",
            files={"file": ("backup.zip", archive, "application/zip")},
        )
        assert restored.status_code == 200
        assert restored.json()["restored"] is True
        assert restored.json()["requires_restart"] is True
        assert not stale.exists()
