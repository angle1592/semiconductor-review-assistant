from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session

from app.shared.database import session_for
from app.study.schemas import ArtifactCreate, ArtifactRead, SourceQuestionRead, SourceQuestionUpdate
from app.study.service import artifact_read, create_artifact, delete_artifact, get_artifact, list_artifacts, list_source_questions, set_source_question_archived, source_question_read, update_source_question


router = APIRouter(tags=["study"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/api/projects/{project_id}/source-questions", response_model=list[SourceQuestionRead])
def questions(project_id: str, session: SessionDependency, archived: bool = False):
    return [source_question_read(item) for item in list_source_questions(session, project_id, archived)]


@router.patch("/api/source-questions/{question_id}", response_model=SourceQuestionRead)
def edit_question(question_id: int, payload: SourceQuestionUpdate, session: SessionDependency):
    return source_question_read(update_source_question(session, question_id, payload))


@router.post("/api/source-questions/{question_id}/archive", response_model=SourceQuestionRead)
def archive_question(question_id: int, session: SessionDependency):
    return source_question_read(set_source_question_archived(session, question_id, True))


@router.post("/api/source-questions/{question_id}/restore", response_model=SourceQuestionRead)
def restore_question(question_id: int, session: SessionDependency):
    return source_question_read(set_source_question_archived(session, question_id, False))


@router.post("/api/projects/{project_id}/artifacts", response_model=ArtifactRead, status_code=status.HTTP_202_ACCEPTED)
def generate(project_id: str, payload: ArtifactCreate, session: SessionDependency):
    artifact, _job = create_artifact(session, project_id, payload)
    return artifact_read(artifact)


@router.get("/api/projects/{project_id}/artifacts", response_model=list[ArtifactRead])
def artifacts(project_id: str, session: SessionDependency):
    return [artifact_read(item) for item in list_artifacts(session, project_id)]


@router.get("/api/artifacts/{artifact_id}", response_model=ArtifactRead)
def artifact(artifact_id: int, session: SessionDependency):
    return artifact_read(get_artifact(session, artifact_id))


@router.delete("/api/artifacts/{artifact_id}", status_code=204)
def remove_artifact(artifact_id: int, session: SessionDependency):
    delete_artifact(session, artifact_id)
    return Response(status_code=204)
