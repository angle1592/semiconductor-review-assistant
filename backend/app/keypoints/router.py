from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session

from app.keypoints.schemas import (
    CandidateBulkAction,
    CandidateBulkResult,
    CandidateRead,
    CandidateUpdate,
    KeyPointCreate,
    KeyPointRead,
    KeyPointReorder,
    KeyPointUpdate,
)
from app.keypoints.service import (
    bulk_candidate_action,
    candidate_read,
    create_keypoint,
    delete_keypoint,
    keypoint_read,
    list_candidates,
    list_keypoints,
    reorder_keypoints,
    update_candidate,
    update_keypoint,
)
from app.shared.database import session_for


router = APIRouter(tags=["keypoints"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


@router.get(
    "/api/analysis-runs/{run_id}/candidates",
    response_model=list[CandidateRead],
)
def list_candidates_endpoint(run_id: int, session: SessionDependency):
    return [candidate_read(candidate) for candidate in list_candidates(session, run_id)]


@router.patch("/api/keypoint-candidates/{candidate_id}", response_model=CandidateRead)
def update_candidate_endpoint(
    candidate_id: int,
    payload: CandidateUpdate,
    session: SessionDependency,
):
    return candidate_read(update_candidate(session, candidate_id, payload))


@router.post(
    "/api/keypoint-candidates:bulk-action",
    response_model=CandidateBulkResult,
)
def bulk_candidate_action_endpoint(
    payload: CandidateBulkAction,
    session: SessionDependency,
):
    confirmed, rejected, keypoint_ids = bulk_candidate_action(
        session,
        confirm_ids=payload.confirm_ids,
        reject_ids=payload.reject_ids,
    )
    return {
        "confirmed": confirmed,
        "rejected": rejected,
        "keypoint_ids": keypoint_ids,
    }


@router.post(
    "/api/projects/{project_id}/keypoints",
    response_model=KeyPointRead,
    status_code=status.HTTP_201_CREATED,
)
def create_keypoint_endpoint(
    project_id: str,
    payload: KeyPointCreate,
    session: SessionDependency,
):
    return keypoint_read(create_keypoint(session, project_id, payload))


@router.get("/api/projects/{project_id}/keypoints", response_model=list[KeyPointRead])
def list_keypoints_endpoint(project_id: str, session: SessionDependency):
    return [keypoint_read(point) for point in list_keypoints(session, project_id)]


@router.patch("/api/keypoints/{keypoint_id}", response_model=KeyPointRead)
def update_keypoint_endpoint(
    keypoint_id: int,
    payload: KeyPointUpdate,
    session: SessionDependency,
):
    return keypoint_read(update_keypoint(session, keypoint_id, payload))


@router.delete("/api/keypoints/{keypoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keypoint_endpoint(keypoint_id: int, session: SessionDependency) -> Response:
    delete_keypoint(session, keypoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/projects/{project_id}/keypoints:reorder",
    response_model=list[KeyPointRead],
)
def reorder_keypoints_endpoint(
    project_id: str,
    payload: KeyPointReorder,
    session: SessionDependency,
):
    return [
        keypoint_read(point)
        for point in reorder_keypoints(session, project_id, payload.ordered_ids)
    ]
