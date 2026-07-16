import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.repository import create_analysis_run
from app.jobs.models import DurableJob
from app.jobs.service import enqueue_job
from app.projects.models import ReviewProject
from app.shared.database import create_database


def test_analysis_run_persists_reproducible_snapshots_and_batches(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    with Session(engine) as session:
        project = ReviewProject(name="状态机复习")
        session.add(project)
        session.commit()

        run = create_analysis_run(
            session,
            project_id=project.id,
            selected_block_ids=["block-a", "block-b", "block-c"],
            prompt_snapshot="优先公式与易错点",
            provider_id="provider-1",
            provider_config_generation=7,
            model_id="review-model",
            schema_version="candidate-v1",
            pipeline_version="analysis-v1",
            batches=[["block-a", "block-b"], ["block-c"]],
        )

        stored = session.get(AnalysisRun, run.id)
        batches = session.exec(
            select(AnalysisBatch)
            .where(AnalysisBatch.run_id == run.id)
            .order_by(AnalysisBatch.ordinal)
        ).all()

    assert stored is not None
    assert stored.status == "queued"
    assert json.loads(stored.selected_block_ids_json) == ["block-a", "block-b", "block-c"]
    assert stored.prompt_snapshot == "优先公式与易错点"
    assert stored.provider_config_generation == 7
    assert stored.total_batches == 2
    assert [json.loads(batch.block_ids_json) for batch in batches] == [
        ["block-a", "block-b"],
        ["block-c"],
    ]
    assert [batch.status for batch in batches] == ["queued", "queued"]


@pytest.mark.parametrize("secret_key", ["api_key", "token", "authorization", "client_secret"])
def test_job_payload_rejects_credentials(tmp_path: Path, secret_key: str):
    engine = create_database(tmp_path / "data")
    with Session(engine) as session:
        with pytest.raises(ValueError, match="credential"):
            enqueue_job(session, "analysis_run", {"run_id": 1, secret_key: "private"})

        assert session.exec(select(DurableJob)).all() == []


def test_job_payload_is_canonical_and_contains_only_public_work_reference(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    with Session(engine) as session:
        job = enqueue_job(session, "analysis_run", {"run_id": 42, "priority": "normal"})
        stored = session.get(DurableJob, job.id)

    assert stored is not None
    assert stored.payload_json == '{"priority":"normal","run_id":42}'
    assert stored.status == "queued"
    assert stored.attempts == 0
