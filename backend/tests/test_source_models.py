import hashlib

import pytest

from app.sources.models import SourceBlock, SourceDocument
from app.sources.repository import make_block_id
from app.sources.schemas import SourceDocumentCreate


def test_block_identity_is_stable_for_same_document_and_locator():
    expected = hashlib.sha256(b"sha256-a\0page:3:block:2\0parser-v1").hexdigest()

    first = make_block_id("sha256-a", "page:3:block:2", "parser-v1")
    second = make_block_id("sha256-a", "page:3:block:2", "parser-v1")

    assert first == second == expected
    assert first != make_block_id("sha256-a", "page:3:block:3", "parser-v1")


def test_source_document_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="不支持的资料格式"):
        SourceDocumentCreate(project_id="project-1", filename="archive.zip")


def test_source_document_accepts_supported_extension_case_insensitively():
    source = SourceDocumentCreate(
        project_id="project-1",
        filename="Questions.PPTX",
        source_kind="question_bank",
    )

    assert source.extension == ".pptx"
    assert source.source_kind == "question_bank"


def test_source_tables_use_explicit_snake_case_names():
    assert SourceDocument.__tablename__ == "source_document"
    assert SourceBlock.__tablename__ == "source_block"
    assert SourceBlock.model_fields["document_id"].foreign_key == "source_document.id"
