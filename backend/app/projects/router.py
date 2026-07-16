from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlmodel import Session

from app.projects.models import ReviewProjectCreate, ReviewProjectRead, ReviewProjectUpdate
from app.projects.service import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    project_deletion_impact,
    update_project,
)
from app.shared.database import session_for
from app.sources.schemas import DeletionImpact, DeletionResult


router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


@router.post("", response_model=ReviewProjectRead, status_code=status.HTTP_201_CREATED)
def create_project_endpoint(
    payload: ReviewProjectCreate,
    session: SessionDependency,
):
    return create_project(session, payload)


@router.get("", response_model=list[ReviewProjectRead])
def list_projects_endpoint(session: SessionDependency):
    return list_projects(session)


@router.get("/{project_id}", response_model=ReviewProjectRead)
def get_project_endpoint(project_id: str, session: SessionDependency):
    return get_project(session, project_id)


@router.patch("/{project_id}", response_model=ReviewProjectRead)
def update_project_endpoint(
    project_id: str,
    payload: ReviewProjectUpdate,
    session: SessionDependency,
):
    return update_project(session, project_id, payload)


@router.get("/{project_id}/deletion-impact", response_model=DeletionImpact)
def project_deletion_impact_endpoint(
    request: Request,
    project_id: str,
    session: SessionDependency,
):
    return project_deletion_impact(session, project_id, request.app.state.paths.data)


@router.delete("/{project_id}", response_model=DeletionResult)
def delete_project_endpoint(
    request: Request,
    project_id: str,
    session: SessionDependency,
):
    impact = delete_project(
        session,
        project_id,
        data_dir=request.app.state.paths.data,
        runtime_dir=request.app.state.paths.runtime,
    )
    return {"deleted": impact}
