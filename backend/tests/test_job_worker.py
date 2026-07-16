from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.repository import (
    create_analysis_run,
    process_analysis_batches,
    request_run_cancellation,
)
from app.jobs.models import DurableJob
from app.jobs.repository import (
    claim_next_job,
    complete_job,
    heartbeat_job,
    retry_or_fail_job,
)
from app.jobs.service import enqueue_job
from app.jobs.worker import DurableWorker
from app.projects.models import ReviewProject
from app.shared.database import create_database


NOW = datetime(2026, 7, 16, 6, 0, tzinfo=UTC)


def create_engine_with_project(tmp_path: Path):
    engine = create_database(tmp_path / "data")
    with Session(engine) as session:
        project = ReviewProject(name="worker 测试")
        session.add(project)
        session.commit()
        session.refresh(project)
        return engine, project.id


def test_only_one_worker_claims_a_queued_job_atomically(tmp_path: Path):
    engine, _ = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        job_id = enqueue_job(session, "analysis_run", {"run_id": 1}, now=NOW).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda worker_id: claim_next_job(
                    engine,
                    worker_id=worker_id,
                    now=NOW,
                    lease_seconds=30,
                ),
                ["worker-a", "worker-b"],
            )
        )

    claimed = [job for job in claims if job is not None]
    assert len(claimed) == 1
    assert claimed[0].id == job_id
    assert claimed[0].attempts == 1
    assert claimed[0].status == "running"


def test_expired_lease_is_recovered_and_heartbeat_prevents_early_reclaim(tmp_path: Path):
    engine, _ = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        job_id = enqueue_job(session, "analysis_run", {"run_id": 1}, now=NOW).id

    first = claim_next_job(engine, worker_id="worker-a", now=NOW, lease_seconds=10)
    assert first is not None
    assert heartbeat_job(
        engine,
        job_id,
        worker_id="worker-a",
        now=NOW + timedelta(seconds=5),
        lease_seconds=10,
    )
    assert (
        claim_next_job(
            engine,
            worker_id="worker-b",
            now=NOW + timedelta(seconds=11),
            lease_seconds=10,
        )
        is None
    )

    recovered = claim_next_job(
        engine,
        worker_id="worker-b",
        now=NOW + timedelta(seconds=16),
        lease_seconds=10,
    )
    assert recovered is not None
    assert recovered.id == job_id
    assert recovered.worker_id == "worker-b"
    assert recovered.attempts == 2


def test_retry_backoff_and_terminal_failure_are_persisted(tmp_path: Path):
    engine, _ = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        job_id = enqueue_job(
            session,
            "analysis_run",
            {"run_id": 1},
            max_attempts=2,
            now=NOW,
        ).id

    first = claim_next_job(engine, worker_id="worker-a", now=NOW, lease_seconds=30)
    assert first is not None
    state = retry_or_fail_job(
        engine,
        job_id,
        worker_id="worker-a",
        public_error_code="UPSTREAM_TIMEOUT",
        error_detail="TimeoutError",
        now=NOW,
        base_delay_seconds=20,
    )
    assert state == "retry_wait"

    with Session(engine) as session:
        waiting = session.get(DurableJob, job_id)
        assert waiting is not None
        assert waiting.status == "retry_wait"
        assert waiting.available_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=20)
        assert waiting.public_error_code == "UPSTREAM_TIMEOUT"
        assert waiting.error_detail == "TimeoutError"

    assert (
        claim_next_job(
            engine,
            worker_id="worker-b",
            now=NOW + timedelta(seconds=19),
            lease_seconds=30,
        )
        is None
    )
    second = claim_next_job(
        engine,
        worker_id="worker-b",
        now=NOW + timedelta(seconds=20),
        lease_seconds=30,
    )
    assert second is not None
    assert second.attempts == 2
    terminal = retry_or_fail_job(
        engine,
        job_id,
        worker_id="worker-b",
        public_error_code="UPSTREAM_TIMEOUT",
        error_detail="TimeoutError",
        now=NOW + timedelta(seconds=20),
        base_delay_seconds=20,
    )
    assert terminal == "failed"


def test_cancellation_is_observed_between_batches(tmp_path: Path):
    engine, project_id = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        run = create_analysis_run(
            session,
            project_id=project_id,
            selected_block_ids=["a", "b"],
            prompt_snapshot="",
            provider_id="provider",
            provider_config_generation=1,
            model_id="model",
            schema_version="v1",
            pipeline_version="v1",
            batches=[["a"], ["b"]],
        )
        run_id = run.id

    called: list[tuple[str, ...]] = []

    def handler(_batch_id: int, block_ids: tuple[str, ...]):
        called.append(block_ids)
        with Session(engine) as session:
            request_run_cancellation(session, run_id)
        return {"ok": True}

    process_analysis_batches(engine, run_id, handler)

    with Session(engine) as session:
        batches = session.exec(
            select(AnalysisBatch)
            .where(AnalysisBatch.run_id == run_id)
            .order_by(AnalysisBatch.ordinal)
        ).all()
        run = session.get(AnalysisRun, run_id)

    assert called == [("a",)]
    assert [batch.status for batch in batches] == ["succeeded", "skipped"]
    assert run is not None
    assert run.status == "cancelled"
    assert run.completed_batches == 1


def test_restart_resumes_pending_batches_without_repeating_success(tmp_path: Path):
    engine, project_id = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        run = create_analysis_run(
            session,
            project_id=project_id,
            selected_block_ids=["a", "b", "c"],
            prompt_snapshot="",
            provider_id="provider",
            provider_config_generation=1,
            model_id="model",
            schema_version="v1",
            pipeline_version="v1",
            batches=[["a"], ["b"], ["c"]],
        )
        run_id = run.id

    called: list[tuple[str, ...]] = []

    def handler(_batch_id: int, block_ids: tuple[str, ...]):
        called.append(block_ids)
        return {"blocks": block_ids}

    process_analysis_batches(engine, run_id, handler, max_batches=1)
    process_analysis_batches(engine, run_id, handler)

    assert called == [("a",), ("b",), ("c",)]
    with Session(engine) as session:
        batches = session.exec(
            select(AnalysisBatch)
            .where(AnalysisBatch.run_id == run_id)
            .order_by(AnalysisBatch.ordinal)
        ).all()
    assert [batch.status for batch in batches] == ["succeeded", "succeeded", "succeeded"]
    assert all(batch.attempts == 1 for batch in batches)


def test_restart_recovers_a_batch_left_running_by_a_crashed_process(tmp_path: Path):
    engine, project_id = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        run = create_analysis_run(
            session,
            project_id=project_id,
            selected_block_ids=["a"],
            prompt_snapshot="",
            provider_id="provider",
            provider_config_generation=1,
            model_id="model",
            schema_version="v1",
            pipeline_version="v1",
            batches=[["a"]],
        )
        run_id = run.id

    def crash(_batch_id: int, _block_ids: tuple[str, ...]):
        raise RuntimeError("simulated process exit")

    try:
        process_analysis_batches(engine, run_id, crash)
    except RuntimeError:
        pass

    recovered: list[tuple[str, ...]] = []
    process_analysis_batches(
        engine,
        run_id,
        lambda _batch_id, block_ids: recovered.append(block_ids) or {"ok": True},
    )

    with Session(engine) as session:
        batch = session.exec(
            select(AnalysisBatch).where(AnalysisBatch.run_id == run_id)
        ).one()
    assert recovered == [("a",)]
    assert batch.status == "succeeded"
    assert batch.attempts == 2


def test_worker_redacts_handler_errors_before_persisting_retry_state(tmp_path: Path):
    engine, _ = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        job_id = enqueue_job(session, "analysis_run", {"run_id": 1}, now=NOW).id

    worker = DurableWorker(
        engine,
        {"analysis_run": lambda _payload: (_ for _ in ()).throw(RuntimeError("api_key=sk-private"))},
        worker_id="worker-a",
        retry_base_seconds=10,
    )
    assert worker.run_once(now=NOW)

    with Session(engine) as session:
        job = session.get(DurableJob, job_id)
    assert job is not None
    assert job.status == "retry_wait"
    assert "sk-private" not in job.error_detail
    assert "[REDACTED]" in job.error_detail


def test_job_completion_requires_the_current_lease_owner(tmp_path: Path):
    engine, _ = create_engine_with_project(tmp_path)
    with Session(engine) as session:
        job_id = enqueue_job(session, "analysis_run", {"run_id": 1}, now=NOW).id
    assert claim_next_job(engine, worker_id="worker-a", now=NOW, lease_seconds=30)

    assert complete_job(engine, job_id, worker_id="worker-b", now=NOW) is False
    assert complete_job(engine, job_id, worker_id="worker-a", now=NOW) is True
