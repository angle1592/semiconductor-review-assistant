from sqlmodel import Session, select

from app.projects.models import (
    ReviewProject,
    ReviewProjectCreate,
    ReviewProjectUpdate,
    utc_now,
)
from app.shared.errors import NotFoundError


def create_project(session: Session, payload: ReviewProjectCreate) -> ReviewProject:
    project = ReviewProject.model_validate(payload)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def list_projects(session: Session) -> list[ReviewProject]:
    statement = select(ReviewProject).order_by(ReviewProject.created_at.desc())
    return list(session.exec(statement).all())


def get_project(session: Session, project_id: str) -> ReviewProject:
    project = session.get(ReviewProject, project_id)
    if project is None:
        raise NotFoundError("Review project", project_id)
    return project


def update_project(
    session: Session,
    project_id: str,
    payload: ReviewProjectUpdate,
) -> ReviewProject:
    project = get_project(session, project_id)
    project.sqlmodel_update(payload.model_dump(exclude_unset=True))
    project.updated_at = utc_now()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def project_deletion_impact(session: Session, project_id: str, data_dir):
    from app.sources.service import project_deletion_impact as source_project_deletion_impact

    return source_project_deletion_impact(session, project_id, data_dir)


def delete_project(session: Session, project_id: str, *, data_dir, runtime_dir):
    from app.sources.service import delete_project_cascade

    return delete_project_cascade(
        session,
        project_id,
        data_dir=data_dir,
        runtime_dir=runtime_dir,
    )
