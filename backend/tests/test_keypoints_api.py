import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.keypoints.models import KeyPoint, KeyPointCandidate
from app.main import create_app
from app.providers.credentials import MemorySecretStore
from tests.test_analysis_api import run_payload, seed_project_materials


def complete_run_with_candidates(app, run_id: int, *, suffix: str = ""):
    with Session(app.state.database) as session:
        run = session.get(AnalysisRun, run_id)
        batch = session.exec(select(AnalysisBatch).where(AnalysisBatch.run_id == run_id)).one()
        batch.status = "succeeded"
        batch.result_json = json.dumps(
            {
                "candidates": [
                    {
                        "title": f"带隙定义{suffix}",
                        "explanation": "价带顶与导带底之间的能量差。",
                        "importance": "core",
                        "source_block_ids": ["paragraph-a"],
                        "evidence_quotes": ["公式说明与易错点"],
                        "rationale": "基础定义",
                    },
                    {
                        "title": f"易错点{suffix}",
                        "explanation": "不要混淆带隙与功函数。",
                        "importance": "important",
                        "source_block_ids": ["paragraph-a"],
                        "evidence_quotes": ["易错点"],
                        "rationale": "常见错误",
                    },
                ],
                "source_questions": [],
            },
            ensure_ascii=False,
        )
        run.status = "succeeded"
        run.completed_batches = 1
        session.add(batch)
        session.add(run)
        session.commit()


def create_completed_run(
    client, app, project_id, provider_id, model_profile_id, block_ids, suffix=""
):
    created = client.post(
        f"/api/projects/{project_id}/analysis-runs",
        json=run_payload(
            provider_id,
            model_profile_id,
            {"mode": "selected_blocks", "block_ids": block_ids},
        ),
    ).json()
    complete_run_with_candidates(app, created["run_id"], suffix=suffix)
    return created["run_id"]


def test_candidates_are_editable_then_bulk_confirmed_or_rejected(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, provider_id, model_profile_id, block_ids = seed_project_materials(app)

    with TestClient(app) as client:
        run_id = create_completed_run(
            client, app, project_id, provider_id, model_profile_id, block_ids
        )
        candidates = client.get(f"/api/analysis-runs/{run_id}/candidates")
        assert candidates.status_code == 200
        assert len(candidates.json()) == 2
        first, second = candidates.json()
        assert all(item["status"] == "pending" for item in candidates.json())

        edited = client.patch(
            f"/api/keypoint-candidates/{first['id']}",
            json={"title": "带隙核心定义", "importance": "important"},
        )
        assert edited.status_code == 200
        assert edited.json()["title"] == "带隙核心定义"
        assert edited.json()["user_edited"] is True

        bulk = client.post(
            "/api/keypoint-candidates:bulk-action",
            json={
                "confirm_ids": [first["id"]],
                "reject_ids": [second["id"]],
            },
        )
        assert bulk.status_code == 200
        assert bulk.json()["confirmed"] == 1
        assert bulk.json()["rejected"] == 1

        points = client.get(f"/api/projects/{project_id}/keypoints")
        assert points.status_code == 200
        assert [point["title"] for point in points.json()] == ["带隙核心定义"]
        assert points.json()[0]["origin"] == "ai"
        assert points.json()[0]["user_edited"] is True

        immutable = client.patch(
            f"/api/keypoint-candidates/{first['id']}",
            json={"title": "不允许再次编辑"},
        )
        assert immutable.status_code == 409


def test_rerun_keeps_confirmed_points_and_deduplicates_reconfirmation(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, provider_id, model_profile_id, block_ids = seed_project_materials(app)

    with TestClient(app) as client:
        first_run = create_completed_run(
            client, app, project_id, provider_id, model_profile_id, block_ids
        )
        first_candidate = client.get(f"/api/analysis-runs/{first_run}/candidates").json()[0]
        client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [first_candidate["id"]], "reject_ids": []},
        )

        second_run = create_completed_run(
            client, app, project_id, provider_id, model_profile_id, block_ids
        )
        second_candidates = client.get(f"/api/analysis-runs/{second_run}/candidates").json()
        assert second_run != first_run
        assert {item["run_id"] for item in second_candidates} == {second_run}
        second_same = next(item for item in second_candidates if item["title"] == "带隙定义")
        confirmed = client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [second_same["id"]], "reject_ids": []},
        )
        assert confirmed.status_code == 200

        points = client.get(f"/api/projects/{project_id}/keypoints").json()
        assert len(points) == 1
        assert points[0]["title"] == "带隙定义"


def test_manual_keypoint_crud_and_reorder(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, *_ = seed_project_materials(app)

    with TestClient(app) as client:
        first = client.post(
            f"/api/projects/{project_id}/keypoints",
            json={
                "title": "定义",
                "explanation": "基础定义",
                "importance": "core",
                "source_block_ids": ["heading-a"],
                "evidence_quotes": [],
            },
        )
        second = client.post(
            f"/api/projects/{project_id}/keypoints",
            json={
                "title": "公式",
                "explanation": "重要公式",
                "importance": "important",
                "source_block_ids": ["paragraph-a"],
                "evidence_quotes": ["公式说明"],
            },
        )
        assert first.status_code == second.status_code == 201

        reordered = client.post(
            f"/api/projects/{project_id}/keypoints:reorder",
            json={"ordered_ids": [second.json()["id"], first.json()["id"]]},
        )
        assert reordered.status_code == 200
        assert [item["id"] for item in reordered.json()] == [
            second.json()["id"],
            first.json()["id"],
        ]

        updated = client.patch(
            f"/api/keypoints/{first.json()['id']}",
            json={"explanation": "已人工修订"},
        )
        assert updated.status_code == 200
        assert updated.json()["user_edited"] is True
        assert client.delete(f"/api/keypoints/{second.json()['id']}").status_code == 204
        remaining = client.get(f"/api/projects/{project_id}/keypoints").json()
        assert [item["id"] for item in remaining] == [first.json()["id"]]

    with Session(app.state.database) as session:
        assert len(session.exec(select(KeyPoint)).all()) == 1
        assert len(session.exec(select(KeyPointCandidate)).all()) == 0


def test_source_deletion_reports_and_cascades_generated_review_data(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    project_id, provider_id, model_profile_id, block_ids = seed_project_materials(app)

    with TestClient(app) as client:
        run_id = create_completed_run(
            client, app, project_id, provider_id, model_profile_id, block_ids
        )
        candidates = client.get(f"/api/analysis-runs/{run_id}/candidates").json()
        client.post(
            "/api/keypoint-candidates:bulk-action",
            json={"confirm_ids": [candidates[0]["id"]], "reject_ids": []},
        )
        with Session(app.state.database) as session:
            from app.sources.models import SourceDocument

            source_id = session.exec(
                select(SourceDocument.id).where(SourceDocument.project_id == project_id)
            ).one()

        impact = client.get(f"/api/sources/{source_id}/deletion-impact")
        assert impact.status_code == 200
        assert impact.json()["candidates"] == 2
        assert impact.json()["generated_artifacts"] == 1
        deleted = client.delete(f"/api/sources/{source_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == impact.json()

    with Session(app.state.database) as session:
        assert session.exec(select(KeyPointCandidate)).all() == []
        assert session.exec(select(KeyPoint)).all() == []
        assert session.exec(select(AnalysisRun)).all() == []
        assert session.exec(select(AnalysisBatch)).all() == []
