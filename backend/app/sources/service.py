from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import mimetypes
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import tempfile
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import func
from sqlmodel import Session, select

from app.projects.models import ReviewProject
from app.shared.errors import AppError, NotFoundError
from app.sources.models import SourceBlock, SourceDocument
from app.sources.parse_cache import ParseCache, parse_cache_key
from app.sources.parsers import parse_source
from app.sources.parsers.contracts import ParsedSource
from app.sources.repository import make_block_id
from app.sources.schemas import DeletionImpact, SourceDocumentUpdate


Parser = Callable[[Path, Path], ParsedSource]
SOURCE_PARSER_VERSION = "1"
DEFAULT_SOURCE_MAX_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class ParseOutcome:
    parsed: ParsedSource
    cache_status: str


class SourceParsingService:
    def __init__(self, cache: ParseCache, parsers: dict[str, Parser] | None = None):
        self.cache = cache
        self.parsers = parsers or {}

    def parse(
        self,
        source: Path,
        file_sha256: str,
        parser_version: str,
        output_dir: Path,
    ) -> ParseOutcome:
        key = parse_cache_key(file_sha256, parser_version)
        cached = self.cache.load(key)
        if cached is not None:
            self.cache.materialize(key, cached, output_dir)
            return ParseOutcome(cached, "hit")

        parser = self.parsers.get(source.suffix.lower(), parse_source)
        parsed = parser(source, output_dir)
        self.cache.store(key, parser_version, parsed, output_dir)
        return ParseOutcome(parsed, "miss")


def _warnings(document: SourceDocument) -> list[str]:
    if not document.parse_message:
        return []
    try:
        value = json.loads(document.parse_message)
        return [str(item) for item in value] if isinstance(value, list) else []
    except json.JSONDecodeError:
        return [document.parse_message]


def source_read(document: SourceDocument) -> dict[str, object]:
    return {
        "id": document.id,
        "project_id": document.project_id,
        "display_name": document.original_name,
        "extension": document.extension,
        "media_type": document.media_type,
        "byte_size": document.byte_size,
        "sha256": document.sha256,
        "source_kind": document.source_kind,
        "parse_status": document.parse_status,
        "parser_version": document.parser_version,
        "page_count": document.page_count,
        "warnings": _warnings(document),
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def get_source(session: Session, source_id: int) -> SourceDocument:
    document = session.get(SourceDocument, source_id)
    if document is None:
        raise NotFoundError("Source", str(source_id))
    return document


def list_sources(
    session: Session,
    project_id: str,
    *,
    offset: int,
    limit: int,
) -> tuple[list[SourceDocument], int]:
    if session.get(ReviewProject, project_id) is None:
        raise NotFoundError("Review project", project_id)
    base = select(SourceDocument).where(SourceDocument.project_id == project_id)
    total = session.exec(
        select(func.count())
        .select_from(SourceDocument)
        .where(SourceDocument.project_id == project_id)
    ).one()
    documents = session.exec(
        base.order_by(SourceDocument.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return list(documents), int(total)


def list_source_blocks(
    session: Session,
    source_id: int,
    *,
    offset: int,
    limit: int,
) -> tuple[list[SourceBlock], int]:
    get_source(session, source_id)
    condition = SourceBlock.document_id == source_id
    total = session.exec(select(func.count()).select_from(SourceBlock).where(condition)).one()
    blocks = session.exec(
        select(SourceBlock)
        .where(condition)
        .order_by(SourceBlock.ordinal)
        .offset(offset)
        .limit(limit)
    ).all()
    return list(blocks), int(total)


def block_read(block: SourceBlock) -> dict[str, object]:
    try:
        heading_path = json.loads(block.heading_path_json)
    except json.JSONDecodeError:
        heading_path = []
    return {
        "id": block.id,
        "ordinal": block.ordinal,
        "locator": block.locator,
        "kind": block.kind,
        "text": block.text,
        "page_number": block.page_number,
        "heading_path": heading_path,
        "preview_path": block.asset_path,
    }


def update_source(
    session: Session,
    source_id: int,
    payload: SourceDocumentUpdate,
) -> SourceDocument:
    document = get_source(session, source_id)
    changes = payload.model_dump(exclude_unset=True)
    if "display_name" in changes:
        document.original_name = changes.pop("display_name")
    for field, value in changes.items():
        setattr(document, field, value)
    document.updated_at = datetime.now(UTC)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def _clean_filename(filename: str | None) -> str:
    cleaned = PurePosixPath((filename or "").replace("\\", "/")).name.strip()
    if not cleaned:
        raise AppError(
            code="INVALID_FILENAME",
            message="文件名为空，请重新选择资料。",
            status_code=422,
            action="select_file",
        )
    return cleaned


def _validate_extension(filename: str) -> str:
    from app.sources.schemas import SUPPORTED_SOURCE_EXTENSIONS

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_SOURCE_EXTENSIONS:
        raise AppError(
            code="UNSUPPORTED_SOURCE_FORMAT",
            message="不支持此资料格式。请选择 PDF、Word、PPT、TXT 或 Markdown 文件。",
            status_code=422,
            action="select_supported_file",
            context={"filename": filename},
        )
    return extension


def _write_upload(
    stream: BinaryIO,
    target: Path,
    *,
    filename: str,
    max_bytes: int,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise AppError(
                    code="FILE_TOO_LARGE",
                    message=f"文件超过 {max_bytes} 字节上限，请压缩或拆分后重试。",
                    status_code=413,
                    action="select_smaller_file",
                    context={"filename": filename, "max_bytes": max_bytes},
                )
            digest.update(chunk)
            output.write(chunk)
    return size, digest.hexdigest()


def _existing_upload(
    session: Session,
    project_id: str,
    file_sha256: str,
) -> SourceDocument | None:
    return session.exec(
        select(SourceDocument).where(
            SourceDocument.project_id == project_id,
            SourceDocument.sha256 == file_sha256,
            SourceDocument.parser_version == SOURCE_PARSER_VERSION,
        )
    ).first()


def ingest_source(
    session: Session,
    *,
    project_id: str,
    filename: str | None,
    media_type: str | None,
    source_kind: str,
    stream: BinaryIO,
    data_dir: Path,
    parser: SourceParsingService,
    max_bytes: int,
) -> dict[str, object]:
    if session.get(ReviewProject, project_id) is None:
        raise NotFoundError("Review project", project_id)
    clean_name = _clean_filename(filename)
    extension = _validate_extension(clean_name)
    incoming_root = data_dir / "sources" / ".incoming"
    incoming_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="upload-", dir=incoming_root))
    source_path = temporary / f"source{extension}"
    formal_dir: Path | None = None
    try:
        byte_size, file_sha256 = _write_upload(
            stream,
            source_path,
            filename=clean_name,
            max_bytes=max_bytes,
        )
        existing = _existing_upload(session, project_id, file_sha256)
        if existing is not None:
            block_count = session.exec(
                select(func.count())
                .select_from(SourceBlock)
                .where(SourceBlock.document_id == existing.id)
            ).one()
            return {
                "source_id": existing.id,
                "parse_status": existing.parse_status,
                "page_count": existing.page_count,
                "block_count": int(block_count),
                "cache": "hit",
                "warnings": _warnings(existing),
            }

        assets = temporary / "assets"
        try:
            outcome = parser.parse(
                source_path,
                file_sha256,
                SOURCE_PARSER_VERSION,
                assets,
            )
        except AppError as error:
            if not error.context:
                error.context = {"filename": clean_name}
            raise
        except Exception as error:
            encrypted = any(word in str(error).lower() for word in ("encrypted", "password"))
            raise AppError(
                code="FILE_ENCRYPTED" if encrypted else "FILE_PARSE_FAILED",
                message=(
                    "文件受密码保护，请移除密码后重试。"
                    if encrypted
                    else "文件无法解析，可能已损坏或格式不完整，请重新导出后重试。"
                ),
                status_code=422,
                action="remove_password" if encrypted else "reexport_file",
                context={"filename": clean_name},
            ) from error

        storage_id = uuid4().hex
        formal_dir = data_dir / "sources" / project_id / storage_id
        formal_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary), formal_dir)
        relative_source = (formal_dir / source_path.name).relative_to(data_dir).as_posix()
        parsed = outcome.parsed
        warnings = list(parsed.warnings)
        document = SourceDocument(
            project_id=project_id,
            original_name=clean_name,
            stored_name=relative_source,
            extension=extension,
            media_type=media_type
            or mimetypes.guess_type(clean_name)[0]
            or "application/octet-stream",
            byte_size=byte_size,
            sha256=file_sha256,
            source_kind=source_kind,
            parse_status="degraded" if warnings else "ready",
            parser_version=SOURCE_PARSER_VERSION,
            page_count=parsed.page_count,
            parse_message=json.dumps(warnings, ensure_ascii=False) if warnings else None,
        )
        session.add(document)
        session.flush()
        for ordinal, block in enumerate(parsed.blocks):
            session.add(
                SourceBlock(
                    id=make_block_id(file_sha256, block.locator, SOURCE_PARSER_VERSION),
                    document_id=document.id,
                    ordinal=ordinal,
                    locator=block.locator,
                    kind=block.kind,
                    text=block.text,
                    page_number=block.page_number,
                    heading_path_json=json.dumps(block.heading_path, ensure_ascii=False),
                    asset_path=block.asset_path,
                )
            )
        session.commit()
        session.refresh(document)
        return {
            "source_id": document.id,
            "parse_status": document.parse_status,
            "page_count": document.page_count,
            "block_count": len(parsed.blocks),
            "cache": outcome.cache_status,
            "warnings": warnings,
        }
    except Exception:
        session.rollback()
        if formal_dir is not None and formal_dir.exists():
            shutil.rmtree(formal_dir)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _source_root(document: SourceDocument, data_dir: Path) -> Path:
    source_path = (data_dir / document.stored_name).resolve()
    source_path.relative_to((data_dir / "sources").resolve())
    return source_path.parent


def preview_asset(document: SourceDocument, data_dir: Path, asset_path: str) -> Path:
    root = (_source_root(document, data_dir) / "assets").resolve()
    candidate_path = PurePosixPath(asset_path.replace("\\", "/"))
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        raise AppError(
            code="INVALID_PREVIEW_PATH",
            message="预览路径无效。",
            status_code=400,
        )
    candidate = (root / Path(*candidate_path.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise AppError(
            code="INVALID_PREVIEW_PATH",
            message="预览路径无效。",
            status_code=400,
        ) from error
    if not candidate.is_file():
        raise NotFoundError("Preview asset", asset_path)
    return candidate


def _asset_count(document: SourceDocument, data_dir: Path) -> int:
    assets = _source_root(document, data_dir) / "assets"
    return sum(1 for path in assets.rglob("*") if path.is_file()) if assets.is_dir() else 0


def source_deletion_impact(
    session: Session,
    source_id: int,
    data_dir: Path,
) -> DeletionImpact:
    document = get_source(session, source_id)
    block_count = session.exec(
        select(func.count()).select_from(SourceBlock).where(SourceBlock.document_id == source_id)
    ).one()
    return DeletionImpact(
        sources=1,
        blocks=int(block_count),
        preview_assets=_asset_count(document, data_dir),
    )


def project_deletion_impact(
    session: Session,
    project_id: str,
    data_dir: Path,
) -> DeletionImpact:
    if session.get(ReviewProject, project_id) is None:
        raise NotFoundError("Review project", project_id)
    documents = session.exec(
        select(SourceDocument).where(SourceDocument.project_id == project_id)
    ).all()
    impact = DeletionImpact()
    for document in documents:
        impact += source_deletion_impact(session, document.id, data_dir)
    return impact


def _stage_for_deletion(source_root: Path, runtime_dir: Path) -> tuple[Path, Path] | None:
    if not source_root.exists():
        return None
    trash = runtime_dir / "deletion-trash" / uuid4().hex
    trash.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_root), trash)
    return source_root, trash


def _restore_staged(staged: tuple[Path, Path] | None) -> None:
    if staged is None:
        return
    original, trash = staged
    if trash.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(trash), original)


def _discard_staged(staged: tuple[Path, Path] | None) -> None:
    if staged is not None and staged[1].exists():
        shutil.rmtree(staged[1])


def delete_source(
    session: Session,
    source_id: int,
    *,
    data_dir: Path,
    runtime_dir: Path,
) -> DeletionImpact:
    document = get_source(session, source_id)
    impact = source_deletion_impact(session, source_id, data_dir)
    staged = _stage_for_deletion(_source_root(document, data_dir), runtime_dir)
    try:
        blocks = session.exec(select(SourceBlock).where(SourceBlock.document_id == source_id)).all()
        for block in blocks:
            session.delete(block)
        session.delete(document)
        session.commit()
    except Exception:
        session.rollback()
        _restore_staged(staged)
        raise
    _discard_staged(staged)
    return impact


def delete_project_cascade(
    session: Session,
    project_id: str,
    *,
    data_dir: Path,
    runtime_dir: Path,
) -> DeletionImpact:
    project = session.get(ReviewProject, project_id)
    if project is None:
        raise NotFoundError("Review project", project_id)
    impact = project_deletion_impact(session, project_id, data_dir)
    project_root = data_dir / "sources" / project_id
    staged = _stage_for_deletion(project_root, runtime_dir)
    try:
        documents = session.exec(
            select(SourceDocument).where(SourceDocument.project_id == project_id)
        ).all()
        document_ids = [document.id for document in documents]
        if document_ids:
            blocks = session.exec(
                select(SourceBlock).where(SourceBlock.document_id.in_(document_ids))
            ).all()
            for block in blocks:
                session.delete(block)
        for document in documents:
            session.delete(document)
        session.delete(project)
        session.commit()
    except Exception:
        session.rollback()
        _restore_staged(staged)
        raise
    _discard_staged(staged)
    return impact
