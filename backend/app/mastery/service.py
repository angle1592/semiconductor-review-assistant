from datetime import UTC, datetime
import json

from sqlmodel import Session, select

from app.keypoints.models import KeyPoint
from app.mastery.models import MasteryRecord, StudyAttempt
from app.mastery.schemas import MasteryUpdate, StudyAttemptCreate
from app.shared.errors import NotFoundError
from app.study.models import GeneratedArtifact, SourceQuestion


TARGET_MODELS = {"keypoint": KeyPoint, "source_question": SourceQuestion, "artifact": GeneratedArtifact}


def _validate_target(session: Session, project_id: str, target_type: str, target_id: int):
    model = TARGET_MODELS[target_type]
    target = session.get(model, target_id)
    if target is None or target.project_id != project_id:
        raise NotFoundError(target_type, str(target_id))
    return target


def attempt_read(attempt: StudyAttempt) -> dict[str, object]:
    return {
        **attempt.model_dump(exclude={"response_json"}),
        "response": json.loads(attempt.response_json) if attempt.response_json else None,
    }


def mastery_read(record: MasteryRecord) -> dict[str, object]:
    return record.model_dump()


def _upsert(session: Session, project_id: str, target_type: str, target_id: int, level: str, last_attempt_at=None):
    record = session.exec(select(MasteryRecord).where(MasteryRecord.project_id == project_id, MasteryRecord.target_type == target_type, MasteryRecord.target_id == target_id)).first()
    if record is None:
        record = MasteryRecord(project_id=project_id, target_type=target_type, target_id=target_id)
    record.level = level
    if last_attempt_at is not None:
        record.last_attempt_at = last_attempt_at
    record.updated_at = datetime.now(UTC)
    session.add(record)
    session.flush()
    return record


def create_attempt(session: Session, project_id: str, payload: StudyAttemptCreate):
    _validate_target(session, project_id, payload.item_type, payload.item_id)
    attempt = StudyAttempt(project_id=project_id, mode=payload.mode, item_type=payload.item_type, item_id=payload.item_id, response_json=json.dumps(payload.response, ensure_ascii=False, sort_keys=True) if payload.response is not None else None, correct=payload.correct, self_rating=payload.self_rating)
    session.add(attempt)
    session.flush()
    if payload.self_rating is not None:
        _upsert(session, project_id, payload.item_type, payload.item_id, payload.self_rating, attempt.created_at)
    session.commit()
    session.refresh(attempt)
    return attempt


def update_mastery(session: Session, project_id: str, target_type: str, target_id: int, payload: MasteryUpdate):
    _validate_target(session, project_id, target_type, target_id)
    record = _upsert(session, project_id, target_type, target_id, payload.level)
    session.commit()
    session.refresh(record)
    return record


def list_mastery(session: Session, project_id: str, level: str | None = None, target_type: str | None = None):
    statement = select(MasteryRecord).where(MasteryRecord.project_id == project_id)
    if level:
        statement = statement.where(MasteryRecord.level == level)
    if target_type:
        statement = statement.where(MasteryRecord.target_type == target_type)
    return list(session.exec(statement.order_by(MasteryRecord.updated_at.desc())).all())


def mastery_summary(session: Session, project_id: str):
    records = list_mastery(session, project_id)
    by_level = {level: 0 for level in ("unrated", "learning", "familiar", "mastered")}
    by_type: dict[str, int] = {}
    for record in records:
        by_level[record.level] = by_level.get(record.level, 0) + 1
        by_type[record.target_type] = by_type.get(record.target_type, 0) + 1
    return {"total": len(records), "by_level": by_level, "by_type": by_type}
