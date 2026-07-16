from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.contracts import ProviderResult
from app.providers.credentials import MemorySecretStore, credential_key
from app.study.schemas import ArtifactGenerationResult, OutlinePayload, OutlineSection
from app.study.worker_handler import ArtifactWorkerHandler
from tests.test_analysis_api import seed_project_materials


class ArtifactAdapter:
    def __init__(self, calls):
        self.calls = calls

    async def generate_json(self, request):
        self.calls.append(request)
        return ProviderResult(value=ArtifactGenerationResult(outline=OutlinePayload(title="复习提纲", sections=[OutlineSection(heading="带隙", body="核心定义", keypoint_ids=[1])])), model_id=request.model)


def test_generated_outline_uses_confirmed_points_and_exact_cache(tmp_path: Path):
    secrets = MemorySecretStore()
    app = create_app(tmp_path / "data", secret_store=secrets)
    project_id, provider_id, model_id, block_ids = seed_project_materials(app)
    secrets.set(credential_key(provider_id), "private-key")
    calls = []
    with TestClient(app) as client:
        point = client.post(f"/api/projects/{project_id}/keypoints", json={"title": "带隙", "explanation": "核心定义", "importance": "core", "source_block_ids": block_ids, "evidence_quotes": []}).json()
        payload = {"kind": "outline", "keypoint_ids": [point["id"]], "source_question_ids": [], "provider_id": provider_id, "model_profile_id": model_id, "run_override": "按章节组织"}
        created = client.post(f"/api/projects/{project_id}/artifacts", json=payload)
        assert created.status_code == 202
        handler = ArtifactWorkerHandler(app.state.database, app.state.paths.runtime, secrets, lambda _profile, _key: ArtifactAdapter(calls))
        handler({"artifact_id": created.json()["id"]})
        artifact = client.get(f"/api/artifacts/{created.json()['id']}").json()
        assert artifact["status"] == "succeeded"
        assert artifact["keypoint_ids"] == [point["id"]]
        assert artifact["payload"]["outline"]["title"] == "复习提纲"
        assert len(calls) == 1

        repeated = client.post(f"/api/projects/{project_id}/artifacts", json=payload).json()
        handler({"artifact_id": repeated["id"]})
        assert client.get(f"/api/artifacts/{repeated['id']}").json()["cache_status"] == "hit"
        assert len(calls) == 1

        missing_source = client.post(f"/api/projects/{project_id}/artifacts", json={**payload, "kind": "ai_variant"})
        assert missing_source.status_code == 422
        assert missing_source.json()["code"] == "SOURCE_QUESTION_REQUIRED"
        assert missing_source.json()["action"] == "choose_source_questions"
