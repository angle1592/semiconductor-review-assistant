from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch
from app.analysis.repository import process_analysis_batches
from app.analysis.schemas import AnalysisBatchResult, KeyPointCandidate
from app.analysis.worker_handler import AnalysisWorkerHandler
from app.jobs.models import DurableJob
from app.jobs.worker import DurableWorker
from app.main import create_app
from app.providers.contracts import ProviderResult, StructuredRequest
from app.providers.credentials import MemorySecretStore, credential_key
from app.providers.models import AIProviderProfile, ModelProfile
from app.sources.parsers.pptx import parse_pptx


FIXTURES = Path(__file__).parent / "fixtures" / "sources"


class StoryAdapter:
    def __init__(self, state: dict[str, object]):
        self.state = state

    async def generate_json(self, request: StructuredRequest):
        self.state["calls"] = int(self.state.get("calls", 0)) + 1
        if int(self.state.get("failures", 0)):
            self.state["failures"] = int(self.state["failures"]) - 1
            raise RuntimeError("temporary provider failure")
        block_ids = [
            line.removeprefix("BLOCK_ID: ")
            for line in request.prompt.splitlines()
            if line.startswith("BLOCK_ID: ")
        ]
        marker = block_ids[0][:8]
        return ProviderResult(
            value=AnalysisBatchResult(
                candidates=[
                    KeyPointCandidate(
                        title=f"重点 {marker}",
                        explanation="从资料证据中提取的核心定义。",
                        importance="core",
                        source_block_ids=block_ids,
                        evidence_quotes=["核心定义"],
                        rationale="项目规则要求优先定义与易错点",
                    )
                ],
                source_questions=[],
            ),
            model_id=request.model,
        )


def upload(client: TestClient, project_id: str, filename: str):
    path = FIXTURES / filename
    return client.post(
        f"/api/projects/{project_id}/sources",
        data={"source_kind": "mixed"},
        files={"file": (filename, path.read_bytes())},
    )


def seed_provider(app, secrets: MemorySecretStore):
    with Session(app.state.database) as session:
        provider = AIProviderProfile(
            name="故事测试服务",
            protocol="openai_compatible",
            base_url="https://provider.test/v1",
            enabled=True,
            credential_generation=1,
        )
        session.add(provider)
        session.flush()
        first = ModelProfile(
            provider_id=provider.id,
            model_id="review-model",
            display_name="Review Model",
            text_status="passed",
            structured_status="passed",
            vision_status="passed",
        )
        second = ModelProfile(
            provider_id=provider.id,
            model_id="review-model-2",
            display_name="Review Model 2",
            text_status="passed",
            structured_status="passed",
            vision_status="passed",
        )
        session.add(first)
        session.add(second)
        session.commit()
        secrets.set(credential_key(provider.id), "story-private-key")
        return provider.id, first.id, second.id


def run_payload(provider_id: str, model_id: str, scope: dict, prompt: str = ""):
    return {
        "scope": scope,
        "provider_id": provider_id,
        "model_profile_id": model_id,
        "run_override": prompt,
        "parameters": {"temperature": 0},
        "confirm_large_range": True,
    }


def execute(app, secrets, state, run_id: int):
    handler = AnalysisWorkerHandler(
        app.state.database,
        app.state.paths.runtime,
        secrets,
        lambda _profile, _key: StoryAdapter(state),
        data_dir=app.state.paths.data,
    )
    handler({"run_id": run_id})


def test_upload_selected_analysis_cache_edit_and_confirm_story(tmp_path: Path):
    secrets = MemorySecretStore()
    app = create_app(tmp_path / "data", secret_store=secrets)
    app.state.source_parsing_service.parsers[".pptx"] = (
        lambda source, output: parse_pptx(source, output, renderer=lambda _source, _output: ())
    )
    state: dict[str, object] = {"calls": 0, "failures": 0}

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "全格式总复习",
                "importance_prompt": "优先定义、公式与易错点",
            },
        ).json()
        project_id = project["id"]
        uploaded = {
            name: upload(client, project_id, name)
            for name in ("sample.pdf", "sample.docx", "sample.pptx", "sample.txt", "sample.md")
        }
        assert all(response.status_code == 201 for response in uploaded.values())
        assert all(response.json()["parse_status"] in {"ready", "degraded"} for response in uploaded.values())

        markdown_id = uploaded["sample.md"].json()["source_id"]
        original_blocks = client.get(f"/api/sources/{markdown_id}/blocks").json()["items"]
        repeated = upload(client, project_id, "sample.md")
        repeated_blocks = client.get(f"/api/sources/{repeated.json()['source_id']}/blocks").json()["items"]
        assert repeated.json()["cache"] == "hit"
        assert [block["id"] for block in repeated_blocks] == [block["id"] for block in original_blocks]

        provider_id, model_id, other_model_id = seed_provider(app, secrets)
        selected_ids = [block["id"] for block in original_blocks]
        scope = {"mode": "selected_blocks", "block_ids": selected_ids}

        created = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(provider_id, model_id, scope),
        ).json()
        execute(app, secrets, state, created["run_id"])
        assert state["calls"] == 1

        first_candidate = client.get(
            f"/api/analysis-runs/{created['run_id']}/candidates"
        ).json()[0]
        edited = client.patch(
            f"/api/keypoint-candidates/{first_candidate['id']}",
            json={"rationale": "已人工核对来源和判断理由"},
        )
        assert edited.status_code == 200
        assert edited.json()["user_edited"] is True
        client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [first_candidate["id"]], "reject_ids": []},
        )

        exact = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(provider_id, model_id, scope),
        ).json()
        execute(app, secrets, state, exact["run_id"])
        assert state["calls"] == 1
        with Session(app.state.database) as session:
            exact_batch = session.exec(
                select(AnalysisBatch).where(AnalysisBatch.run_id == exact["run_id"])
            ).one()
            assert exact_batch.cache_status == "hit"

        exact_candidate = client.get(
            f"/api/analysis-runs/{exact['run_id']}/candidates"
        ).json()[0]
        client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [exact_candidate["id"]], "reject_ids": []},
        )
        assert len(client.get(f"/api/projects/{project_id}/keypoints").json()) == 1

        prompt_change = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(provider_id, model_id, scope, "特别关注例外"),
        ).json()
        execute(app, secrets, state, prompt_change["run_id"])
        model_change = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(provider_id, other_model_id, scope),
        ).json()
        execute(app, secrets, state, model_change["run_id"])
        assert state["calls"] == 3


def test_all_sources_worker_crash_resume_and_provider_retry_story(tmp_path: Path):
    secrets = MemorySecretStore()
    app = create_app(
        tmp_path / "data",
        secret_store=secrets,
        analysis_batch_characters=18,
    )
    state: dict[str, object] = {"calls": 0, "failures": 0}

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "恢复测试"}).json()["id"]
        assert upload(client, project_id, "sample.md").status_code == 201
        provider_id, model_id, _ = seed_provider(app, secrets)
        created = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_id,
                {"mode": "all_sources", "block_ids": []},
            ),
        ).json()
        run_id = created["run_id"]
        assert created["batch_count"] >= 2

        first_handler = AnalysisWorkerHandler(
            app.state.database,
            app.state.paths.runtime,
            secrets,
            lambda _profile, _key: StoryAdapter(state),
            data_dir=app.state.paths.data,
        )
        process_analysis_batches(
            app.state.database,
            run_id,
            first_handler._process_batch,
            max_batches=1,
        )
        with Session(app.state.database) as session:
            batches = session.exec(
                select(AnalysisBatch)
                .where(AnalysisBatch.run_id == run_id)
                .order_by(AnalysisBatch.ordinal)
            ).all()
            assert batches[0].status == "succeeded"
            assert batches[0].attempts == 1

        state["failures"] = 1
        resumed_handler = AnalysisWorkerHandler(
            app.state.database,
            app.state.paths.runtime,
            secrets,
            lambda _profile, _key: StoryAdapter(state),
            data_dir=app.state.paths.data,
        )
        now = datetime.now(UTC) + timedelta(seconds=1)
        first_worker = DurableWorker(
            app.state.database,
            {"analysis_run": resumed_handler},
            worker_id="worker-before-restart",
            retry_base_seconds=1,
        )
        assert first_worker.run_once(now=now)
        with Session(app.state.database) as session:
            job = session.exec(
                select(DurableJob).where(DurableJob.kind == "analysis_run")
            ).one()
            assert job.status == "retry_wait"

        restarted_handler = AnalysisWorkerHandler(
            app.state.database,
            app.state.paths.runtime,
            secrets,
            lambda _profile, _key: StoryAdapter(state),
            data_dir=app.state.paths.data,
        )
        restarted_worker = DurableWorker(
            app.state.database,
            {"analysis_run": restarted_handler},
            worker_id="worker-after-restart",
            retry_base_seconds=1,
        )
        assert restarted_worker.run_once(now=now + timedelta(seconds=2))

        progress = client.get(f"/api/analysis-runs/{run_id}").json()
        assert progress["status"] == "succeeded"
        assert progress["completed_batches"] == progress["total_batches"]
        assert progress["batches"][0]["attempts"] == 1
        assert max(batch["attempts"] for batch in progress["batches"]) == 2
        assert state["calls"] == progress["total_batches"] + 1

        candidates = client.get(f"/api/analysis-runs/{run_id}/candidates").json()
        confirmed = client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [candidate["id"] for candidate in candidates], "reject_ids": []},
        )
        assert confirmed.status_code == 200
        points = client.get(f"/api/projects/{project_id}/keypoints").json()
        assert len(points) == len({point["title"] for point in points})
