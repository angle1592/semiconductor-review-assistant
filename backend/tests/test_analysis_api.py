from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.jobs.models import DurableJob
from app.main import create_app
from app.providers.credentials import MemorySecretStore
from app.providers.models import AIProviderProfile, ModelProfile
from app.sources.models import SourceBlock, SourceDocument


def seed_project_materials(app, *, parse_status: str = "ready", with_image: bool = False):
    with Session(app.state.database) as session:
        from app.projects.models import ReviewProject

        project = ReviewProject(name="期末总复习", importance_prompt="优先公式")
        provider = AIProviderProfile(
            name="第三方服务",
            protocol="openai_compatible",
            base_url="https://provider.test/v1",
            enabled=True,
        )
        session.add(project)
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
        document = SourceDocument(
            project_id=project.id,
            original_name="review.md",
            stored_name="sources/review/source.md",
            extension=".md",
            media_type="text/markdown",
            byte_size=20,
            sha256="source-sha",
            source_kind="mixed",
            parse_status=parse_status,
            parser_version="1",
        )
        session.add(model)
        session.add(document)
        session.flush()
        blocks = [
            SourceBlock(
                id="heading-a",
                document_id=document.id,
                ordinal=0,
                locator="heading:1",
                kind="heading",
                text="第一章",
            ),
            SourceBlock(
                id="paragraph-a",
                document_id=document.id,
                ordinal=1,
                locator="paragraph:1",
                kind="paragraph",
                text="公式说明与易错点",
                asset_path="image.png" if with_image else None,
            ),
        ]
        session.add_all(blocks)
        session.commit()
        return project.id, provider.id, model.id, [block.id for block in blocks]


def run_payload(provider_id: str, model_profile_id: str, scope: dict, **overrides):
    payload = {
        "scope": scope,
        "provider_id": provider_id,
        "model_profile_id": model_profile_id,
        "run_override": "本次只看易错点",
        "parameters": {"temperature": 0},
        "confirm_large_range": False,
    }
    payload.update(overrides)
    return payload


def test_create_selected_and_all_source_runs_returns_202_and_progress(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, provider_id, model_profile_id, block_ids = seed_project_materials(app)

    with TestClient(app) as client:
        estimate = client.post(
            f"/api/projects/{project_id}/analysis-range:estimate",
            json={"mode": "selected_blocks", "block_ids": block_ids},
        )
        created = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_profile_id,
                {"mode": "selected_blocks", "block_ids": block_ids},
            ),
        )

        assert estimate.status_code == 200
        assert estimate.json()["block_count"] == 2
        assert estimate.json()["source_count"] == 1
        assert estimate.json()["exceeds_warning"] is False
        assert created.status_code == 202
        body = created.json()
        assert body["status"] == "queued"
        assert body["batch_count"] == 1
        assert "后台继续" in body["message"]

        progress = client.get(f"/api/analysis-runs/{body['run_id']}")
        assert progress.status_code == 200
        assert progress.json()["status"] == "queued"
        assert progress.json()["batches"][0]["status"] == "queued"
        assert progress.json()["completed_batches"] == 0

        all_sources = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_profile_id,
                {"mode": "all_sources"},
            ),
        )
        assert all_sources.status_code == 202
        assert all_sources.json()["run_id"] != body["run_id"]


def test_run_creation_returns_actionable_range_parse_and_capability_errors(tmp_path: Path):
    app = create_app(
        tmp_path / "data",
        secret_store=MemorySecretStore(),
        analysis_warning_blocks=1,
    )
    project_id, provider_id, model_profile_id, block_ids = seed_project_materials(app)

    with TestClient(app) as client:
        empty = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_profile_id,
                {"mode": "selected_blocks", "block_ids": []},
            ),
        )
        excessive = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_profile_id,
                {"mode": "selected_blocks", "block_ids": block_ids},
            ),
        )
        confirmed = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_profile_id,
                {"mode": "selected_blocks", "block_ids": block_ids},
                confirm_large_range=True,
            ),
        )

        assert empty.status_code == 422
        assert empty.json()["code"] == "ANALYSIS_RANGE_EMPTY"
        assert excessive.status_code == 409
        assert excessive.json()["action"] == "select_smaller_range"
        assert confirmed.status_code == 202

    unparsed_app = create_app(tmp_path / "unparsed-data", secret_store=MemorySecretStore())
    unparsed = seed_project_materials(unparsed_app, parse_status="parsing")
    with TestClient(unparsed_app) as client:
        response = client.post(
            f"/api/projects/{unparsed[0]}/analysis-runs",
            json=run_payload(unparsed[1], unparsed[2], {"mode": "all_sources"}),
        )
    assert response.status_code == 409
    assert response.json()["code"] == "SOURCE_NOT_READY"
    assert response.json()["action"] == "wait_for_parsing"

    vision_app = create_app(tmp_path / "vision-data", secret_store=MemorySecretStore())
    vision = seed_project_materials(vision_app, with_image=True)
    with Session(vision_app.state.database) as session:
        model = session.get(ModelProfile, vision[2])
        model.vision_status = "untested"
        session.add(model)
        session.commit()
    with TestClient(vision_app) as client:
        response = client.post(
            f"/api/projects/{vision[0]}/analysis-runs",
            json=run_payload(
                vision[1],
                vision[2],
                {"mode": "selected_blocks", "block_ids": vision[3]},
            ),
        )
    assert response.status_code == 409
    assert response.json()["action"] == "choose_vision_model"


def test_cancel_and_retry_only_failed_batches(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, provider_id, model_profile_id, block_ids = seed_project_materials(app)

    with TestClient(app) as client:
        created = client.post(
            f"/api/projects/{project_id}/analysis-runs",
            json=run_payload(
                provider_id,
                model_profile_id,
                {"mode": "selected_blocks", "block_ids": block_ids},
            ),
        ).json()
        cancel = client.post(f"/api/analysis-runs/{created['run_id']}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["cancellation_requested"] is True

    with Session(app.state.database) as session:
        run = session.get(AnalysisRun, created["run_id"])
        batch = session.exec(select(AnalysisBatch).where(AnalysisBatch.run_id == run.id)).one()
        run.status = "failed"
        run.cancellation_requested = False
        batch.status = "failed"
        batch.attempts = 2
        session.add(run)
        session.add(batch)
        session.commit()
        batch_id = batch.id

    with TestClient(app) as client:
        retried = client.post(f"/api/analysis-runs/{created['run_id']}/retry")
        assert retried.status_code == 202
        assert retried.json()["status"] == "queued"
        assert retried.json()["retried_batch_ids"] == [batch_id]

    with Session(app.state.database) as session:
        batch = session.get(AnalysisBatch, batch_id)
        jobs = session.exec(select(DurableJob)).all()
    assert batch.status == "queued"
    assert batch.attempts == 2
    assert len(jobs) == 2
