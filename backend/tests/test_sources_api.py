from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.credentials import MemorySecretStore


FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def create_project(client: TestClient, name: str = "期末总复习") -> str:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload_fixture(
    client: TestClient,
    project_id: str,
    filename: str,
    *,
    source_kind: str = "mixed",
):
    path = FIXTURES / filename
    return client.post(
        f"/api/projects/{project_id}/sources",
        data={"source_kind": source_kind},
        files={"file": (filename, path.read_bytes())},
    )


def test_source_lifecycle_and_exact_parse_cache(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())

    with TestClient(app) as client:
        project_id = create_project(client)
        created = upload_fixture(client, project_id, "sample.md", source_kind="knowledge")

        assert created.status_code == 201
        payload = created.json()
        assert payload == {
            "source_id": payload["source_id"],
            "parse_status": "ready",
            "page_count": None,
            "block_count": 3,
            "cache": "miss",
            "warnings": [],
        }
        source_id = payload["source_id"]

        source = client.get(f"/api/sources/{source_id}")
        assert source.status_code == 200
        assert source.json()["display_name"] == "sample.md"
        assert source.json()["source_kind"] == "knowledge"
        assert source.json()["project_id"] == project_id

        blocks = client.get(f"/api/sources/{source_id}/blocks", params={"limit": 2})
        assert blocks.status_code == 200
        assert blocks.json()["total"] == 3
        assert blocks.json()["limit"] == 2
        assert [item["ordinal"] for item in blocks.json()["items"]] == [0, 1]
        assert blocks.json()["items"][0]["heading_path"] == ["PN 结复习"]

        updated = client.patch(
            f"/api/sources/{source_id}",
            json={"display_name": "PN 结重点.md", "source_kind": "question_bank"},
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "PN 结重点.md"
        assert updated.json()["source_kind"] == "question_bank"

        invalid_patch = client.patch(
            f"/api/sources/{source_id}",
            json={"display_name": None},
        )
        assert invalid_patch.status_code == 422

        repeated = upload_fixture(client, project_id, "sample.md")
        assert repeated.status_code == 201
        assert repeated.json()["cache"] == "hit"

        impact = client.get(f"/api/sources/{source_id}/deletion-impact")
        assert impact.status_code == 200
        assert impact.json() == {
            "sources": 1,
            "blocks": 3,
            "preview_assets": 0,
            "candidates": 0,
            "source_questions": 0,
            "generated_artifacts": 0,
        }

        deleted = client.delete(f"/api/sources/{source_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == impact.json()
        assert client.get(f"/api/sources/{source_id}").status_code == 404


def test_upload_validates_extension_and_size_before_persistence(tmp_path: Path):
    app = create_app(
        tmp_path / "data",
        secret_store=MemorySecretStore(),
        source_max_bytes=8,
    )

    with TestClient(app) as client:
        project_id = create_project(client)
        unsupported = client.post(
            f"/api/projects/{project_id}/sources",
            files={"file": ("review.exe", b"MZ")},
        )
        too_large = client.post(
            f"/api/projects/{project_id}/sources",
            files={"file": ("review.txt", b"012345678")},
        )

        assert unsupported.status_code == 422
        assert unsupported.json()["code"] == "UNSUPPORTED_SOURCE_FORMAT"
        assert unsupported.json()["action"] == "select_supported_file"
        assert unsupported.json()["context"] == {"filename": "review.exe"}
        assert too_large.status_code == 413
        assert too_large.json()["code"] == "FILE_TOO_LARGE"
        assert too_large.json()["action"] == "select_smaller_file"
        assert too_large.json()["context"]["filename"] == "review.txt"
        assert too_large.json()["context"]["max_bytes"] == 8
        assert client.get(f"/api/projects/{project_id}/sources").json()["total"] == 0


def test_pdf_preview_is_streamed_but_path_traversal_is_blocked(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())

    with TestClient(app) as client:
        project_id = create_project(client)
        created = upload_fixture(client, project_id, "sample.pdf")
        assert created.status_code == 201
        source_id = created.json()["source_id"]

        preview = client.get(f"/api/sources/{source_id}/preview/pages/page-0001.png")
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.content.startswith(b"\x89PNG")

        traversal = client.get(f"/api/sources/{source_id}/preview/%2e%2e%2fsource.pdf")
        assert traversal.status_code == 400
        assert traversal.json()["code"] == "INVALID_PREVIEW_PATH"


def test_corrupt_and_encrypted_files_return_actionable_errors_without_rows(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    encrypted_pdf = tmp_path / "locked.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "locked")
        document.save(
            encrypted_pdf,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="reader",
        )

    with TestClient(app) as client:
        project_id = create_project(client)
        corrupt = client.post(
            f"/api/projects/{project_id}/sources",
            files={"file": ("broken.pdf", b"not a pdf")},
        )
        encrypted = client.post(
            f"/api/projects/{project_id}/sources",
            files={"file": ("locked.pdf", encrypted_pdf.read_bytes())},
        )

        assert corrupt.status_code == 422
        assert corrupt.json()["code"] == "FILE_PARSE_FAILED"
        assert corrupt.json()["action"] == "reexport_file"
        assert corrupt.json()["context"] == {"filename": "broken.pdf"}
        assert encrypted.status_code == 422
        assert encrypted.json()["code"] == "FILE_ENCRYPTED"
        assert encrypted.json()["action"] == "remove_password"
        assert encrypted.json()["context"] == {"filename": "locked.pdf"}
        assert client.get(f"/api/projects/{project_id}/sources").json()["total"] == 0


def test_project_deletion_reports_and_executes_source_cascade(tmp_path: Path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())

    with TestClient(app) as client:
        project_id = create_project(client, "级联删除测试")
        first = upload_fixture(client, project_id, "sample.txt")
        second = upload_fixture(client, project_id, "sample.pdf")
        assert first.status_code == second.status_code == 201

        impact = client.get(f"/api/projects/{project_id}/deletion-impact")
        assert impact.status_code == 200
        assert impact.json()["sources"] == 2
        assert impact.json()["blocks"] == 4
        assert impact.json()["preview_assets"] == 2

        deleted = client.delete(f"/api/projects/{project_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == impact.json()
        assert client.get(f"/api/projects/{project_id}").status_code == 404
        for source_id in (first.json()["source_id"], second.json()["source_id"]):
            assert client.get(f"/api/sources/{source_id}").status_code == 404
