from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.repository import request_run_cancellation
from app.analysis.schemas import (
    AnalysisCancelRead,
    AnalysisRangeEstimate,
    AnalysisRetryRead,
    AnalysisRunCreate,
    AnalysisRunCreated,
    AnalysisRunRead,
    AnalysisScope,
)
from app.analysis.service import (
    estimate_analysis_range,
    resolve_analysis_scope,
    retry_failed_batches,
    schedule_analysis,
)
from app.shared.database import session_for
from app.shared.errors import AppError, NotFoundError


router = APIRouter(tags=["analysis"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


def _run_read(session: Session, run_id: int) -> dict[str, object]:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFoundError("Analysis run", str(run_id))
    batches = session.exec(
        select(AnalysisBatch).where(AnalysisBatch.run_id == run_id).order_by(AnalysisBatch.ordinal)
    ).all()
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "total_batches": run.total_batches,
        "completed_batches": run.completed_batches,
        "failed_batches": run.failed_batches,
        "cancellation_requested": run.cancellation_requested,
        "public_error_code": run.public_error_code,
        "error_detail": run.error_detail,
        "batches": [
            {
                "id": batch.id,
                "ordinal": batch.ordinal,
                "status": batch.status,
                "attempts": batch.attempts,
                "cache_status": batch.cache_status,
                "public_error_code": batch.public_error_code,
                "error_detail": batch.error_detail,
            }
            for batch in batches
        ],
    }


@router.post(
    "/api/projects/{project_id}/analysis-range:estimate",
    response_model=AnalysisRangeEstimate,
)
def estimate_analysis_range_endpoint(
    request: Request,
    project_id: str,
    payload: AnalysisScope,
    session: SessionDependency,
):
    return estimate_analysis_range(
        session,
        project_id,
        mode=payload.mode,
        block_ids=payload.block_ids,
        warning_blocks=request.app.state.analysis_warning_blocks,
    )


@router.post(
    "/api/projects/{project_id}/analysis-runs",
    response_model=AnalysisRunCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis_run_endpoint(
    request: Request,
    project_id: str,
    payload: AnalysisRunCreate,
    session: SessionDependency,
):
    blocks = resolve_analysis_scope(
        session,
        project_id,
        mode=payload.scope.mode,
        block_ids=payload.scope.block_ids,
    )
    if len(blocks) > request.app.state.analysis_warning_blocks and not payload.confirm_large_range:
        raise AppError(
            code="ANALYSIS_RANGE_CONFIRMATION_REQUIRED",
            message="本次范围较大，可能消耗较多时间和第三方额度。请缩小范围或明确确认。",
            status_code=409,
            action="select_smaller_range",
            context={
                "block_count": len(blocks),
                "warning_blocks": request.app.state.analysis_warning_blocks,
            },
        )
    run, job = schedule_analysis(
        session,
        project_id=project_id,
        selected_block_ids=[block.id for block in blocks],
        provider_id=payload.provider_id,
        model_profile_id=payload.model_profile_id,
        run_override=payload.run_override,
        parameters=payload.parameters,
        max_characters=request.app.state.analysis_batch_characters,
        max_images=request.app.state.analysis_batch_images,
    )
    return {
        "run_id": run.id,
        "job_id": job.id,
        "status": run.status,
        "batch_count": run.total_batches,
        "message": "已加入分析队列，可离开此页面；任务会在后台继续。",
    }


@router.get("/api/analysis-runs/{run_id}", response_model=AnalysisRunRead)
def get_analysis_run_endpoint(run_id: int, session: SessionDependency):
    return _run_read(session, run_id)


@router.post("/api/analysis-runs/{run_id}/cancel", response_model=AnalysisCancelRead)
def cancel_analysis_run_endpoint(run_id: int, session: SessionDependency):
    run = request_run_cancellation(session, run_id)
    return {
        "run_id": run.id,
        "status": run.status,
        "cancellation_requested": run.cancellation_requested,
    }


@router.post(
    "/api/analysis-runs/{run_id}/retry",
    response_model=AnalysisRetryRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_analysis_run_endpoint(run_id: int, session: SessionDependency):
    run, job, batch_ids = retry_failed_batches(session, run_id)
    return {
        "run_id": run.id,
        "job_id": job.id,
        "status": run.status,
        "retried_batch_ids": batch_ids,
    }
