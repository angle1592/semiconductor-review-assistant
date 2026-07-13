from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session, select

from app.content.deletion import cascade_course_data
from app.content.service import stage_document_files_for_deletion
from app.courses.models import Course, CourseCreate, CourseRead
from app.shared.database import session_for
from app.shared.errors import NotFoundError


router = APIRouter(prefix="/api/courses", tags=["courses"])


def get_session(request: Request):
    yield from session_for(request.app.state.database)


SessionDependency = Annotated[Session, Depends(get_session)]


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, session: SessionDependency) -> Course:
    course = Course.model_validate(payload)
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


@router.get("", response_model=list[CourseRead])
def list_courses(session: SessionDependency) -> list[Course]:
    return list(session.exec(select(Course)).all())


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, session: SessionDependency) -> Course:
    course = session.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: str, request: Request, session: SessionDependency) -> Response:
    course = session.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course", course_id)
    document_ids = cascade_course_data(session, course)
    staged_files = stage_document_files_for_deletion(
        data_dir=request.app.state.data_dir,
        document_ids=document_ids,
    )
    try:
        session.commit()
    except Exception:
        staged_files.restore()
        raise
    staged_files.purge()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
