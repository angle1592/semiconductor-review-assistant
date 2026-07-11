from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _create_course(client: TestClient) -> str:
    response = client.post("/api/courses", json={"title": "半导体器件", "description": ""})
    assert response.status_code == 201
    return response.json()["id"]


def _two_page_pdf() -> bytes:
    document = fitz.open()
    for text in ("MOSFET threshold voltage", "Thermal oxide growth"):
        page = document.new_page(width=400, height=300)
        page.insert_text((40, 80), text, fontsize=16)
    payload = document.tobytes()
    document.close()
    return payload


def _image_only_pdf() -> bytes:
    source = fitz.open()
    source_page = source.new_page(width=320, height=180)
    source_page.draw_rect(
        fitz.Rect(20, 20, 300, 160),
        color=(0.1, 0.25, 0.55),
        fill=(0.85, 0.9, 0.98),
        width=2,
    )
    source_page.draw_circle(
        fitz.Point(160, 90),
        46,
        color=(0.85, 0.3, 0.12),
        fill=(0.98, 0.72, 0.45),
    )
    raster = source_page.get_pixmap(alpha=False).tobytes("png")
    source.close()

    document = fitz.open()
    page = document.new_page(width=320, height=180)
    page.insert_image(page.rect, stream=raster)
    payload = document.tobytes()
    document.close()
    return payload


def test_pdf_upload_extracts_numbered_pages_and_serves_png_previews(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    pdf_payload = _two_page_pdf()

    with TestClient(app) as client:
        course_id = _create_course(client)
        uploaded = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("week-01.pdf", pdf_payload, "application/pdf")},
        )

        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]
        fetched = client.get(f"/api/documents/{document_id}")

        assert fetched.status_code == 200
        body = fetched.json()
        assert body["course_id"] == course_id
        assert body["original_filename"] == "week-01.pdf"
        assert body["file_type"] == "pdf"
        assert body["page_count"] == 2
        assert [page["page_number"] for page in body["pages"]] == [1, 2]
        assert "MOSFET threshold voltage" in body["pages"][0]["extracted_text"]
        assert body["pages"][0]["source"]["document_id"] == document_id
        assert body["pages"][0]["source"]["filename"] == "week-01.pdf"
        assert body["pages"][0]["source"]["page_number"] == 1

        preview = client.get(body["pages"][0]["preview_url"])
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")

    originals = list((tmp_path / "uploads").rglob("week-01.pdf"))
    assert len(originals) == 1
    assert originals[0].read_bytes() == pdf_payload


def test_image_only_pdf_upload_keeps_page_mapping_without_inventing_text(
    tmp_path: Path,
) -> None:
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        uploaded = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("wafer-map.pdf", _image_only_pdf(), "application/pdf")},
        )

        assert uploaded.status_code == 201
        body = uploaded.json()
        assert body["page_count"] == 1
        assert body["pages"][0]["page_number"] == 1
        assert body["pages"][0]["extracted_text"] == ""
        assert body["pages"][0]["source"] == {
            "document_id": body["id"],
            "filename": "wafer-map.pdf",
            "page_number": 1,
        }

        preview = client.get(body["pages"][0]["preview_url"])

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_notebook_import_preserves_full_raw_text_and_source(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    raw_text = "# PN 结复习\n\n- 空穴扩散\n\n```text\n  保留缩进  \n```\n"

    with TestClient(app) as client:
        course_id = _create_course(client)
        response = client.post(
            f"/api/courses/{course_id}/notebook-imports",
            json={
                "title": "NotebookLM 学习指南",
                "raw_text": raw_text,
                "source_filename": "guide.md",
            },
        )

    assert response.status_code == 201
    assert response.json()["course_id"] == course_id
    assert response.json()["raw_text"] == raw_text
    assert response.json()["source_filename"] == "guide.md"


def test_document_upload_rejects_unknown_extension_and_empty_file(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        unsupported = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("notes.txt", b"content", "text/plain")},
        )
        empty = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        invalid = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": ("broken.pdf", b"not-a-pdf", "application/pdf")},
        )

    assert unsupported.status_code == 422
    assert unsupported.json()["code"] == "UNSUPPORTED_DOCUMENT_TYPE"
    assert empty.status_code == 422
    assert empty.json()["code"] == "EMPTY_DOCUMENT"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_DOCUMENT"
    assert not any(path.is_file() for path in (tmp_path / "uploads").rglob("*"))
    assert not any(path.is_file() for path in (tmp_path / "previews").rglob("*"))


def test_powerpoint_unavailable_is_typed_and_cleans_partial_files(
    tmp_path: Path, monkeypatch
) -> None:
    from app.content import service
    from app.content.errors import PowerPointUnavailableError

    def unavailable(_source_path: Path, _target_path: Path) -> None:
        raise PowerPointUnavailableError()

    monkeypatch.setattr(service, "export_powerpoint_to_pdf", unavailable)
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        response = client.post(
            f"/api/courses/{course_id}/documents",
            files={
                "file": (
                    "lecture.pptx",
                    b"not-a-real-presentation",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            },
        )

    assert response.status_code == 503
    assert response.json()["code"] == "POWERPOINT_UNAVAILABLE"
    assert not list((tmp_path / "uploads").rglob("lecture.pptx"))
    assert not any(path.is_file() for path in (tmp_path / "processed").rglob("*"))
    assert not any(path.is_file() for path in (tmp_path / "previews").rglob("*"))


@pytest.mark.parametrize(
    ("filename", "content_type", "expected_type"),
    [
        ("lecture.ppt", "application/vnd.ms-powerpoint", "ppt"),
        (
            "lecture.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
        ),
    ],
)
def test_powerpoint_successfully_enters_the_pdf_page_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    expected_type: str,
) -> None:
    from app.content import service

    converted_pdf = _two_page_pdf()
    conversion_calls: list[tuple[Path, Path]] = []

    def export_as_pdf(source_path: Path, target_path: Path) -> None:
        conversion_calls.append((source_path, target_path))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(converted_pdf)

    monkeypatch.setattr(service, "export_powerpoint_to_pdf", export_as_pdf)
    app = create_app(data_dir=tmp_path)

    with TestClient(app) as client:
        course_id = _create_course(client)
        uploaded = client.post(
            f"/api/courses/{course_id}/documents",
            files={"file": (filename, b"presentation-source", content_type)},
        )

        assert uploaded.status_code == 201
        body = uploaded.json()
        assert body["file_type"] == expected_type
        assert body["original_filename"] == filename
        assert body["page_count"] == 2
        assert [page["page_number"] for page in body["pages"]] == [1, 2]
        assert "MOSFET threshold voltage" in body["pages"][0]["extracted_text"]
        assert "Thermal oxide growth" in body["pages"][1]["extracted_text"]
        assert all(page["source"]["filename"] == filename for page in body["pages"])

        first_preview = client.get(body["pages"][0]["preview_url"])

    assert first_preview.status_code == 200
    assert first_preview.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(conversion_calls) == 1
    source_path, target_path = conversion_calls[0]
    assert source_path.name == filename
    assert source_path.read_bytes() == b"presentation-source"
    assert target_path.name == "converted.pdf"
    assert target_path.read_bytes() == converted_pdf
