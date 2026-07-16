from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.mastery.schemas import MasteryRead, MasterySummary, MasteryUpdate, StudyAttemptCreate, StudyAttemptRead
from app.mastery.service import attempt_read, create_attempt, list_mastery, mastery_read, mastery_summary, update_mastery
from app.shared.database import session_for


router = APIRouter(tags=["mastery"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


@router.post("/api/projects/{project_id}/study-attempts", response_model=StudyAttemptRead, status_code=201)
def add_attempt(project_id: str, payload: StudyAttemptCreate, session: SessionDependency):
    return attempt_read(create_attempt(session, project_id, payload))


@router.put("/api/projects/{project_id}/mastery/{target_type}/{target_id}", response_model=MasteryRead)
def rate(project_id: str, target_type: str, target_id: int, payload: MasteryUpdate, session: SessionDependency):
    return mastery_read(update_mastery(session, project_id, target_type, target_id, payload))


@router.get("/api/projects/{project_id}/mastery", response_model=list[MasteryRead])
def records(project_id: str, session: SessionDependency, level: str | None = None, target_type: str | None = None):
    return [mastery_read(item) for item in list_mastery(session, project_id, level, target_type)]


@router.get("/api/projects/{project_id}/mastery/summary", response_model=MasterySummary)
def summary(project_id: str, session: SessionDependency):
    return mastery_summary(session, project_id)
