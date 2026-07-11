from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine


def create_database(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = (data_dir / "review.db").resolve()
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def session_for(engine):
    with Session(engine) as session:
        yield session
