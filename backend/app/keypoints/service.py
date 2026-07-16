from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import func
from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.schemas import AnalysisBatchResult
from app.keypoints.models import KeyPoint, KeyPointCandidate
from app.keypoints.schemas import CandidateUpdate, KeyPointCreate, KeyPointUpdate
from app.projects.models import ReviewProject
from app.shared.errors import AppError, NotFoundError
from app.sources.models import SourceBlock, SourceDocument


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _list(value: str) -> list[str]:
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def candidate_read(candidate: KeyPointCandidate) -> dict[str, object]:
    return {
        **candidate.model_dump(exclude={"source_block_ids_json", "evidence_quotes_json"}),
        "source_block_ids": _list(candidate.source_block_ids_json),
        "evidence_quotes": _list(candidate.evidence_quotes_json),
    }


def keypoint_read(point: KeyPoint) -> dict[str, object]:
    return {
        **point.model_dump(
            exclude={"source_block_ids_json", "evidence_quotes_json", "fingerprint"}
        ),
        "source_block_ids": _list(point.source_block_ids_json),
        "evidence_quotes": _list(point.evidence_quotes_json),
    }


def _fingerprint(
    title: str,
    explanation: str,
    source_block_ids: list[str],
) -> str:
    canonical = _json(
        {
            "title": title.strip(),
            "explanation": explanation.strip(),
            "source_block_ids": source_block_ids,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def materialize_run_candidates(session: Session, run_id: int) -> list[KeyPointCandidate]:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFoundError("Analysis run", str(run_id))
    batches = session.exec(
        select(AnalysisBatch)
        .where(
            AnalysisBatch.run_id == run_id,
            AnalysisBatch.status == "succeeded",
        )
        .order_by(AnalysisBatch.ordinal)
    ).all()
    for batch in batches:
        if not batch.result_json:
            continue
        result = AnalysisBatchResult.model_validate_json(batch.result_json)
        for ordinal, item in enumerate(result.candidates):
            existing = session.exec(
                select(KeyPointCandidate).where(
                    KeyPointCandidate.run_id == run_id,
                    KeyPointCandidate.batch_id == batch.id,
                    KeyPointCandidate.ordinal == ordinal,
                )
            ).first()
            if existing is None:
                session.add(
                    KeyPointCandidate(
                        project_id=run.project_id,
                        run_id=run_id,
                        batch_id=batch.id,
                        ordinal=ordinal,
                        title=item.title,
                        explanation=item.explanation,
                        importance=item.importance,
                        source_block_ids_json=_json(item.source_block_ids),
                        evidence_quotes_json=_json(item.evidence_quotes),
                        rationale=item.rationale,
                    )
                )
    session.commit()
    return list(
        session.exec(
            select(KeyPointCandidate)
            .where(KeyPointCandidate.run_id == run_id)
            .order_by(KeyPointCandidate.id)
        ).all()
    )


def list_candidates(session: Session, run_id: int) -> list[KeyPointCandidate]:
    materialize_run_candidates(session, run_id)
    return list(
        session.exec(
            select(KeyPointCandidate)
            .where(KeyPointCandidate.run_id == run_id)
            .order_by(KeyPointCandidate.id)
        ).all()
    )


def get_candidate(session: Session, candidate_id: int) -> KeyPointCandidate:
    candidate = session.get(KeyPointCandidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Key point candidate", str(candidate_id))
    return candidate


def update_candidate(
    session: Session,
    candidate_id: int,
    payload: CandidateUpdate,
) -> KeyPointCandidate:
    candidate = get_candidate(session, candidate_id)
    if candidate.status != "pending":
        raise AppError(
            code="CANDIDATE_NOT_EDITABLE",
            message="候选已确认或拒绝，不能继续编辑。",
            status_code=409,
            action="create_new_analysis",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
    candidate.user_edited = True
    candidate.updated_at = datetime.now(UTC)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def _next_position(session: Session, project_id: str) -> int:
    highest = session.exec(
        select(func.max(KeyPoint.position)).where(KeyPoint.project_id == project_id)
    ).one()
    return int(highest or -1) + 1


def bulk_candidate_action(
    session: Session,
    *,
    confirm_ids: list[int],
    reject_ids: list[int],
) -> tuple[int, int, list[int]]:
    candidates = {
        candidate.id: candidate
        for candidate in session.exec(
            select(KeyPointCandidate).where(KeyPointCandidate.id.in_(set(confirm_ids + reject_ids)))
        ).all()
    }
    if len(candidates) != len(set(confirm_ids + reject_ids)):
        raise NotFoundError("Key point candidate", "selection")
    if any(candidate.status != "pending" for candidate in candidates.values()):
        raise AppError(
            code="CANDIDATE_ALREADY_RESOLVED",
            message="选择中包含已确认或已拒绝的候选。",
            status_code=409,
            action="refresh_candidates",
        )
    keypoint_ids: list[int] = []
    positions: dict[str, int] = {}
    for candidate_id in confirm_ids:
        candidate = candidates[candidate_id]
        source_ids = _list(candidate.source_block_ids_json)
        fingerprint = _fingerprint(candidate.title, candidate.explanation, source_ids)
        point = session.exec(
            select(KeyPoint).where(
                KeyPoint.project_id == candidate.project_id,
                KeyPoint.fingerprint == fingerprint,
            )
        ).first()
        if point is None:
            position = positions.setdefault(
                candidate.project_id,
                _next_position(session, candidate.project_id),
            )
            point = KeyPoint(
                project_id=candidate.project_id,
                title=candidate.title,
                explanation=candidate.explanation,
                importance=candidate.importance,
                source_block_ids_json=candidate.source_block_ids_json,
                evidence_quotes_json=candidate.evidence_quotes_json,
                origin="ai",
                run_id=candidate.run_id,
                user_edited=candidate.user_edited,
                fingerprint=fingerprint,
                position=position,
            )
            positions[candidate.project_id] = position + 1
            session.add(point)
            session.flush()
        candidate.status = "confirmed"
        candidate.confirmed_keypoint_id = point.id
        candidate.updated_at = datetime.now(UTC)
        session.add(candidate)
        keypoint_ids.append(point.id)
    for candidate_id in reject_ids:
        candidate = candidates[candidate_id]
        candidate.status = "rejected"
        candidate.updated_at = datetime.now(UTC)
        session.add(candidate)
    session.commit()
    return len(confirm_ids), len(reject_ids), keypoint_ids


def _validate_source_ids(session: Session, project_id: str, block_ids: list[str]) -> None:
    if not block_ids:
        return
    blocks = session.exec(select(SourceBlock).where(SourceBlock.id.in_(block_ids))).all()
    documents = {
        document.id: document
        for document in session.exec(
            select(SourceDocument).where(
                SourceDocument.id.in_({block.document_id for block in blocks})
            )
        ).all()
    }
    if len(blocks) != len(set(block_ids)) or any(
        documents.get(block.document_id) is None
        or documents[block.document_id].project_id != project_id
        for block in blocks
    ):
        raise AppError(
            code="KEYPOINT_SOURCE_INVALID",
            message="知识点引用了不存在或不属于当前项目的资料块。",
            status_code=422,
            action="refresh_source_blocks",
        )


def create_keypoint(
    session: Session,
    project_id: str,
    payload: KeyPointCreate,
) -> KeyPoint:
    if session.get(ReviewProject, project_id) is None:
        raise NotFoundError("Review project", project_id)
    _validate_source_ids(session, project_id, payload.source_block_ids)
    fingerprint = _fingerprint(payload.title, payload.explanation, payload.source_block_ids)
    existing = session.exec(
        select(KeyPoint).where(
            KeyPoint.project_id == project_id,
            KeyPoint.fingerprint == fingerprint,
        )
    ).first()
    if existing is not None:
        return existing
    point = KeyPoint(
        project_id=project_id,
        title=payload.title,
        explanation=payload.explanation,
        importance=payload.importance,
        source_block_ids_json=_json(payload.source_block_ids),
        evidence_quotes_json=_json(payload.evidence_quotes),
        origin="manual",
        user_edited=True,
        fingerprint=fingerprint,
        position=_next_position(session, project_id),
    )
    session.add(point)
    session.commit()
    session.refresh(point)
    return point


def list_keypoints(session: Session, project_id: str) -> list[KeyPoint]:
    if session.get(ReviewProject, project_id) is None:
        raise NotFoundError("Review project", project_id)
    return list(
        session.exec(
            select(KeyPoint)
            .where(KeyPoint.project_id == project_id)
            .order_by(KeyPoint.position, KeyPoint.id)
        ).all()
    )


def update_keypoint(
    session: Session,
    keypoint_id: int,
    payload: KeyPointUpdate,
) -> KeyPoint:
    point = session.get(KeyPoint, keypoint_id)
    if point is None:
        raise NotFoundError("Key point", str(keypoint_id))
    changes = payload.model_dump(exclude_unset=True)
    source_ids = changes.pop("source_block_ids", _list(point.source_block_ids_json))
    evidence = changes.pop("evidence_quotes", _list(point.evidence_quotes_json))
    _validate_source_ids(session, point.project_id, source_ids)
    for field, value in changes.items():
        setattr(point, field, value)
    point.source_block_ids_json = _json(source_ids)
    point.evidence_quotes_json = _json(evidence)
    point.fingerprint = _fingerprint(point.title, point.explanation, source_ids)
    point.user_edited = True
    point.updated_at = datetime.now(UTC)
    session.add(point)
    session.commit()
    session.refresh(point)
    return point


def delete_keypoint(session: Session, keypoint_id: int) -> None:
    point = session.get(KeyPoint, keypoint_id)
    if point is None:
        raise NotFoundError("Key point", str(keypoint_id))
    project_id = point.project_id
    session.delete(point)
    session.commit()
    for position, remaining in enumerate(list_keypoints(session, project_id)):
        remaining.position = position
        session.add(remaining)
    session.commit()


def reorder_keypoints(
    session: Session,
    project_id: str,
    ordered_ids: list[int],
) -> list[KeyPoint]:
    points = list_keypoints(session, project_id)
    by_id = {point.id: point for point in points}
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(by_id):
        raise AppError(
            code="KEYPOINT_REORDER_INVALID",
            message="排序列表必须完整且不能重复。",
            status_code=422,
            action="refresh_keypoints",
        )
    for position, point_id in enumerate(ordered_ids):
        point = by_id[point_id]
        point.position = position
        session.add(point)
    session.commit()
    return list_keypoints(session, project_id)
