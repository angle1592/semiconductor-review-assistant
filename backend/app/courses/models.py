from uuid import uuid4

from sqlmodel import Field, SQLModel


class CourseFields(SQLModel):
    title: str
    description: str = ""


class Course(CourseFields, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)


class CourseCreate(CourseFields):
    pass


class CourseRead(CourseFields):
    id: str
