from collections.abc import Callable
from datetime import UTC, datetime
import json

from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.shared.errors import NotFoundError


BatchHandler = Callable[[int, tuple[str, ...]], dict[str, object]]


def create_analysis_run(
    session: Session,
    *,
    project_id: str,
    selected_block_ids: list[str],
    prompt_snapshot: str,
    provider_id: str,
    provider_config_generation: int,
    model_id: str,
    schema_version: str,
    pipeline_version: str,
    batches: list[list[str]],
) -> AnalysisRun:
    run = AnalysisRun(
        project_id=project_id,
        selected_block_ids_json=json.dumps(selected_block_ids, separators=(",", ":")),
        prompt_snapshot=prompt_snapshot,
        provider_id=provider_id,
        provider_config_generation=provider_config_generation,
        model_id=model_id,
        schema_version=schema_version,
        pipeline_version=pipeline_version,
        total_batches=len(batches),
    )
    session.add(run)
    session.flush()
    for ordinal, block_ids in enumerate(batches):
        session.add(
            AnalysisBatch(
                run_id=run.id,
                ordinal=ordinal,
                block_ids_json=json.dumps(block_ids, separators=(",", ":")),
            )
        )
    session.commit()
    session.refresh(run)
    return run


def request_run_cancellation(session: Session, run_id: int) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFoundError("Analysis run", str(run_id))
    run.cancellation_requested = True
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _recover_running_batches(session: Session, run_id: int) -> None:
    running = session.exec(
        select(AnalysisBatch).where(
            AnalysisBatch.run_id == run_id,
            AnalysisBatch.status == "running",
        )
    ).all()
    for batch in running:
        batch.status = "queued"
        batch.updated_at = datetime.now(UTC)
        session.add(batch)


def _refresh_progress(session: Session, run: AnalysisRun) -> list[AnalysisBatch]:
    batches = session.exec(
        select(AnalysisBatch).where(AnalysisBatch.run_id == run.id).order_by(AnalysisBatch.ordinal)
    ).all()
    run.completed_batches = sum(batch.status == "succeeded" for batch in batches)
    run.failed_batches = sum(batch.status == "failed" for batch in batches)
    return list(batches)


def process_analysis_batches(
    engine,
    run_id: int,
    handler: BatchHandler,
    *,
    max_batches: int | None = None,
) -> None:
    with Session(engine) as session:
        run = session.get(AnalysisRun, run_id)
        if run is None:
            raise NotFoundError("Analysis run", str(run_id))
        if run.status in {"succeeded", "failed", "cancelled"}:
            return
        _recover_running_batches(session, run_id)
        run.status = "running"
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()

    processed = 0
    while max_batches is None or processed < max_batches:
        with Session(engine) as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise NotFoundError("Analysis run", str(run_id))
            batches = _refresh_progress(session, run)
            if run.cancellation_requested:
                for batch in batches:
                    if batch.status == "queued":
                        batch.status = "skipped"
                        batch.updated_at = datetime.now(UTC)
                        session.add(batch)
                run.status = "cancelled"
                run.updated_at = datetime.now(UTC)
                session.add(run)
                session.commit()
                return
            batch = next((item for item in batches if item.status == "queued"), None)
            if batch is None:
                run.status = "partial" if run.failed_batches else "succeeded"
                run.updated_at = datetime.now(UTC)
                session.add(run)
                session.commit()
                return
            batch.status = "running"
            batch.attempts += 1
            batch.updated_at = datetime.now(UTC)
            session.add(batch)
            session.commit()
            batch_id = batch.id
            block_ids = tuple(json.loads(batch.block_ids_json))

        result = handler(batch_id, block_ids)

        with Session(engine) as session:
            stored_batch = session.get(AnalysisBatch, batch_id)
            run = session.get(AnalysisRun, run_id)
            if stored_batch is None or run is None:
                raise RuntimeError("Analysis state disappeared during batch execution")
            if stored_batch.status == "running":
                stored_batch.status = "succeeded"
                stored_batch.result_json = json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stored_batch.updated_at = datetime.now(UTC)
                session.add(stored_batch)
            _refresh_progress(session, run)
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()
        processed += 1
