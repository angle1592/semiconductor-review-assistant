import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.analysis.schemas import AnalysisBatchResult, ExtractedQuestion, KeyPointCandidate
from app.analysis.worker_handler import AnalysisWorkerHandler
from app.main import create_app
from app.providers.contracts import ProviderResult
from app.providers.credentials import MemorySecretStore, credential_key
from app.providers.models import AIProviderProfile, ModelProfile
from app.study.schemas import (
    ArtifactGenerationResult,
    FlashcardPayload,
    OutlinePayload,
    OutlineSection,
    PracticeQuestionPayload,
)
from app.study.worker_handler import ArtifactWorkerHandler


PRIVATE_KEY = "full-story-private-key-861904"
PRIVATE_SOURCE = "private-study-source-417205"


class AnalysisAdapter:
    async def generate_json(self, request):
        block_ids = [
            line.removeprefix("BLOCK_ID: ")
            for line in request.prompt.splitlines()
            if line.startswith("BLOCK_ID: ")
        ]
        return ProviderResult(
            value=AnalysisBatchResult(
                candidates=[
                    KeyPointCandidate(
                        title="能量守恒",
                        explanation="系统总能量在转换中保持不变。",
                        importance="core",
                        source_block_ids=block_ids,
                        evidence_quotes=["总能量保持不变"],
                        rationale="符合项目中对定义的优先规则",
                    )
                ],
                source_questions=[
                    ExtractedQuestion(
                        question="什么是能量守恒？",
                        answer="系统总能量在转换中保持不变。",
                        source_block_ids=block_ids,
                        evidence_quotes=["总能量保持不变"],
                    )
                ],
            ),
            model_id=request.model,
        )


class ArtifactAdapter:
    async def generate_json(self, request):
        payload = json.loads(request.prompt)
        kind = payload["kind"]
        point_id = payload["keypoints"][0]["id"]
        question_ids = [item["id"] for item in payload["source_questions"]]
        if kind == "outline":
            value = ArtifactGenerationResult(
                outline=OutlinePayload(
                    title="期末总复习提纲",
                    sections=[
                        OutlineSection(
                            heading="核心定律",
                            body="能量守恒的定义与使用边界。",
                            keypoint_ids=[point_id],
                        )
                    ],
                )
            )
        elif kind == "flashcard":
            value = ArtifactGenerationResult(
                flashcards=[
                    FlashcardPayload(
                        front="能量守恒描述了什么？",
                        back="封闭系统总能量在转换中保持不变。",
                        keypoint_ids=[point_id],
                    )
                ]
            )
        else:
            value = ArtifactGenerationResult(
                questions=[
                    PracticeQuestionPayload(
                        question=f"{kind}：判断能量转换是否守恒。",
                        answer="守恒。",
                        explanation="能量只发生形式转换。",
                        origin=kind,
                        source_question_ids=question_ids,
                        keypoint_ids=[point_id],
                    )
                ]
            )
        return ProviderResult(value=value, model_id=request.model)


def seed_provider(app, secrets: MemorySecretStore):
    with Session(app.state.database) as session:
        provider = AIProviderProfile(
            name="故事验证服务",
            protocol="openai_compatible",
            base_url="https://provider.test/v1",
            enabled=True,
            credential_generation=1,
        )
        session.add(provider)
        session.flush()
        model = ModelProfile(
            provider_id=provider.id,
            model_id="review-model",
            display_name="Review Model",
            text_status="passed",
            structured_status="passed",
            vision_status="passed",
        )
        session.add(model)
        session.commit()
        secrets.set(credential_key(provider.id), PRIVATE_KEY)
        return provider.id, model.id


def test_shiyao_story_from_source_to_restore_and_redacted_diagnostics(tmp_path):
    secrets = MemorySecretStore()
    app = create_app(tmp_path / "Data", secret_store=secrets)

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "跨学科总复习",
                "description": "完整发布故事",
                "importance_prompt": "优先定义、公式与易错原因",
            },
        ).json()
        project_id = project["id"]
        uploaded = client.post(
            f"/api/projects/{project_id}/sources",
            data={"source_kind": "mixed"},
            files={
                "file": (
                    "energy.md",
                    f"# 能量守恒\n\n系统总能量保持不变。{PRIVATE_SOURCE}".encode(),
                    "text/markdown",
                )
            },
        )
        assert uploaded.status_code == 201
        source_id = uploaded.json()["source_id"]
        blocks = client.get(f"/api/sources/{source_id}/blocks").json()["items"]
        assert blocks

        provider_id, model_id = seed_provider(app, secrets)
        created = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json={
                "scope": {
                    "mode": "selected_blocks",
                    "block_ids": [block["id"] for block in blocks],
                },
                "provider_id": provider_id,
                "model_profile_id": model_id,
                "run_override": "先找定义",
                "parameters": {"temperature": 0},
                "confirm_large_range": True,
            },
        )
        assert created.status_code == 202
        AnalysisWorkerHandler(
            app.state.database,
            app.state.paths.runtime,
            secrets,
            lambda _profile, _key: AnalysisAdapter(),
            data_dir=app.state.paths.data,
        )({"run_id": created.json()["run_id"]})

        candidates = client.get(
            f"/api/analysis-runs/{created.json()['run_id']}/candidates"
        ).json()
        questions = client.get(
            f"/api/projects/{project_id}/source-questions"
        ).json()
        assert len(candidates) == len(questions) == 1
        edited_question = client.patch(
            f"/api/source-questions/{questions[0]['id']}",
            json={"answer_text": "人工核对：封闭系统总能量保持不变。"},
        ).json()
        assert edited_question["user_edited"] is True
        confirmed = client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [candidates[0]["id"]], "reject_ids": []},
        )
        assert confirmed.status_code == 200
        point = client.get(f"/api/projects/{project_id}/keypoints").json()[0]

        artifact_ids = []
        for kind in ("outline", "flashcard", "ai_new", "ai_variant", "ai_error_cause"):
            response = client.post(
                f"/api/projects/{project_id}/artifacts",
                json={
                    "kind": kind,
                    "keypoint_ids": [point["id"]],
                    "source_question_ids": [questions[0]["id"]],
                    "provider_id": provider_id,
                    "model_profile_id": model_id,
                    "run_override": "保持简洁",
                },
            )
            assert response.status_code == 202
            artifact_id = response.json()["id"]
            ArtifactWorkerHandler(
                app.state.database,
                app.state.paths.runtime,
                secrets,
                lambda _profile, _key: ArtifactAdapter(),
            )({"artifact_id": artifact_id})
            artifact = client.get(f"/api/artifacts/{artifact_id}").json()
            assert artifact["status"] == "succeeded"
            assert artifact["keypoint_ids"] == [point["id"]]
            artifact_ids.append(artifact_id)

        attempt = client.post(
            f"/api/projects/{project_id}/study-attempts",
            json={
                "mode": "flashcards",
                "item_type": "artifact",
                "item_id": artifact_ids[1],
                "correct": True,
                "self_rating": "familiar",
            },
        )
        assert attempt.status_code == 201
        rated = client.put(
            f"/api/projects/{project_id}/mastery/keypoint/{point['id']}",
            json={"level": "mastered"},
        )
        assert rated.status_code == 200
        summary = client.get(f"/api/projects/{project_id}/mastery/summary").json()
        assert summary["by_level"]["familiar"] == 1
        assert summary["by_level"]["mastered"] == 1

        backup = client.get("/api/backups/export")
        assert backup.status_code == 200
        validated = client.post(
            "/api/backups/validate",
            files={"file": ("shiyao-backup.zip", backup.content, "application/zip")},
        ).json()
        assert validated["valid"] is True
        assert validated["manifest"]["product"] == "shiyao"

        app.state.paths.logs.mkdir(parents=True, exist_ok=True)
        (app.state.paths.logs / "app.log").write_text(
            f"Authorization: Bearer {PRIVATE_KEY}\nrequest failed safely\n",
            encoding="utf-8",
        )
        diagnostics = client.get("/api/system/diagnostics")
        assert diagnostics.status_code == 200
        with ZipFile(BytesIO(diagnostics.content)) as archive:
            combined = b"".join(archive.read(name) for name in archive.namelist())
            diagnostic_summary = json.loads(archive.read("summary.json"))
        assert diagnostic_summary["providers"][0]["protocol"] == "openai_compatible"
        assert PRIVATE_KEY.encode() not in combined
        assert PRIVATE_SOURCE.encode() not in combined
        assert b"request failed safely" in combined

        restored = client.post(
            "/api/backups/restore",
            files={"file": ("shiyao-backup.zip", backup.content, "application/zip")},
        )
        assert restored.status_code == 200
        assert restored.json()["requires_restart"] is True
