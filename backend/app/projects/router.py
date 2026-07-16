from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session

from app.projects.models import ReviewProjectCreate, ReviewProjectRead, ReviewProjectUpdate
from app.projects.service import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from app.shared.database import session_for


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


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(project_id: str, session: SessionDependency) -> Response:
    delete_project(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
