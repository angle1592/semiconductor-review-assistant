from datetime import UTC, datetime
import hashlib
import json

from sqlmodel import Session, select

from app.analysis.models import AnalysisBatch, AnalysisRun
from app.analysis.schemas import AnalysisBatchResult
from app.analysis.service import hash_text
from app.jobs.service import enqueue_job
from app.keypoints.models import KeyPoint
from app.providers.models import AIProviderProfile, ModelProfile
from app.shared.errors import AppError, NotFoundError
from app.sources.models import SourceBlock
from app.study.models import GeneratedArtifact, SourceQuestion
from app.study.schemas import ArtifactCreate, SourceQuestionUpdate


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ids(value: str) -> list[int]:
    return [int(item) for item in json.loads(value)]


def source_question_read(question: SourceQuestion) -> dict[str, object]:
    return {
        **question.model_dump(exclude={"source_block_ids_json", "evidence_quotes_json", "fingerprint"}),
        "source_block_ids": json.loads(question.source_block_ids_json),
        "evidence_quotes": json.loads(question.evidence_quotes_json),
    }


def artifact_read(artifact: GeneratedArtifact) -> dict[str, object]:
    return {
        **artifact.model_dump(
            exclude={
                "payload_json", "keypoint_ids_json", "source_question_ids_json",
                "provider_id", "provider_config_generation", "provider_protocol",
                "provider_base_url", "model_id", "prompt_snapshot", "prompt_hash",
            }
        ),
        "payload": json.loads(artifact.payload_json),
        "keypoint_ids": _ids(artifact.keypoint_ids_json),
        "source_question_ids": _ids(artifact.source_question_ids_json),
    }


def materialize_run_source_questions(session: Session, run_id: int) -> list[SourceQuestion]:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFoundError("Analysis run", str(run_id))
    batches = session.exec(
        select(AnalysisBatch).where(
            AnalysisBatch.run_id == run_id,
            AnalysisBatch.status == "succeeded",
        )
    ).all()
    for batch in batches:
        if not batch.result_json:
            continue
        result = AnalysisBatchResult.model_validate_json(batch.result_json)
        for item in result.source_questions:
            blocks = session.exec(
                select(SourceBlock).where(SourceBlock.id.in_(item.source_block_ids))
            ).all()
            document_ids = {block.document_id for block in blocks}
            if len(document_ids) != 1:
                continue
            document_id = document_ids.pop()
            normalized = " ".join(item.question.casefold().split())
            fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            existing = session.exec(
                select(SourceQuestion).where(
                    SourceQuestion.document_id == document_id,
                    SourceQuestion.fingerprint == fingerprint,
                )
            ).first()
            if existing is None:
                session.add(
                    SourceQuestion(
                        project_id=run.project_id,
                        document_id=document_id,
                        question_text=item.question,
                        answer_text=item.answer,
                        source_block_ids_json=_json(item.source_block_ids),
                        evidence_quotes_json=_json(item.evidence_quotes),
                        fingerprint=fingerprint,
                        run_id=run_id,
                    )
                )
    session.commit()
    return list(session.exec(select(SourceQuestion).where(SourceQuestion.project_id == run.project_id)).all())


def list_source_questions(session: Session, project_id: str, archived: bool = False):
    return list(session.exec(select(SourceQuestion).where(SourceQuestion.project_id == project_id, SourceQuestion.archived == archived).order_by(SourceQuestion.id)).all())


def get_source_question(session: Session, question_id: int) -> SourceQuestion:
    question = session.get(SourceQuestion, question_id)
    if question is None:
        raise NotFoundError("Source question", str(question_id))
    return question


def update_source_question(session: Session, question_id: int, payload: SourceQuestionUpdate):
    question = get_source_question(session, question_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(question, field, value)
    question.user_edited = True
    question.updated_at = datetime.now(UTC)
    session.add(question)
    session.commit()
    session.refresh(question)
    return question


def set_source_question_archived(session: Session, question_id: int, archived: bool):
    question = get_source_question(session, question_id)
    question.archived = archived
    question.updated_at = datetime.now(UTC)
    session.add(question)
    session.commit()
    session.refresh(question)
    return question


def create_artifact(session: Session, project_id: str, payload: ArtifactCreate):
    keypoints = session.exec(select(KeyPoint).where(KeyPoint.id.in_(payload.keypoint_ids))).all()
    if len(keypoints) != len(set(payload.keypoint_ids)) or any(point.project_id != project_id for point in keypoints):
        raise AppError(code="INVALID_KEYPOINT_SELECTION", message="请选择本项目已确认的重点。", status_code=422, action="select_confirmed_keypoints")
    questions = session.exec(select(SourceQuestion).where(SourceQuestion.id.in_(payload.source_question_ids))).all() if payload.source_question_ids else []
    if len(questions) != len(set(payload.source_question_ids)) or any(question.project_id != project_id or question.archived for question in questions):
        raise AppError(code="INVALID_SOURCE_QUESTION_SELECTION", message="请选择本项目未归档的原题。", status_code=422, action="choose_source_questions")
    if payload.kind in {"ai_variant", "ai_error_cause"} and not questions:
        raise AppError(code="SOURCE_QUESTION_REQUIRED", message="变式题和错因题至少需要一道原题。", status_code=422, action="choose_source_questions")
    provider = session.get(AIProviderProfile, payload.provider_id)
    model = session.get(ModelProfile, payload.model_profile_id)
    if provider is None or not provider.enabled:
        raise AppError(code="PROVIDER_NOT_ENABLED", message="所选第三方服务尚未启用。", status_code=409, action="open_provider_settings")
    if model is None or model.provider_id != provider.id or model.structured_status != "passed":
        raise AppError(code="MODEL_CAPABILITY_NOT_VALIDATED", message="模型尚未通过结构化输出校验。", status_code=409, action="open_provider_settings")
    prompt = f"生成类型：{payload.kind}\n本次补充：{payload.run_override.strip() or '无'}"
    artifact = GeneratedArtifact(
        project_id=project_id,
        kind=payload.kind,
        keypoint_ids_json=_json(payload.keypoint_ids),
        source_question_ids_json=_json(payload.source_question_ids),
        provider_id=provider.id,
        provider_config_generation=provider.credential_generation,
        provider_protocol=provider.protocol,
        provider_base_url=provider.base_url,
        model_id=model.model_id,
        prompt_snapshot=prompt,
        prompt_hash=hash_text(prompt),
    )
    session.add(artifact)
    session.flush()
    job = enqueue_job(session, "artifact_generation", {"artifact_id": artifact.id})
    session.refresh(artifact)
    return artifact, job


def list_artifacts(session: Session, project_id: str):
    return list(session.exec(select(GeneratedArtifact).where(GeneratedArtifact.project_id == project_id).order_by(GeneratedArtifact.id.desc())).all())


def get_artifact(session: Session, artifact_id: int) -> GeneratedArtifact:
    artifact = session.get(GeneratedArtifact, artifact_id)
    if artifact is None:
        raise NotFoundError("Generated artifact", str(artifact_id))
    return artifact


def delete_artifact(session: Session, artifact_id: int) -> None:
    artifact = get_artifact(session, artifact_id)
    session.delete(artifact)
    session.commit()
