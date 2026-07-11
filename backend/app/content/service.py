import platform
import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import fitz

from app.content.errors import (
    EmptyDocumentError,
    InvalidDocumentError,
    PowerPointUnavailableError,
    UnsupportedDocumentTypeError,
)
from app.content.models import Document, Page


SUPPORTED_EXTENSIONS = {".pdf", ".ppt", ".pptx"}


def export_powerpoint_to_pdf(source_path: Path, target_path: Path) -> None:
    if platform.system() != "Windows":
        raise PowerPointUnavailableError()

    try:
        import pythoncom
        from win32com.client import DispatchEx
    except ImportError as error:
        raise PowerPointUnavailableError() from error

    powerpoint = None
    presentation = None
    initialized = False
    try:
        pythoncom.CoInitialize()
        initialized = True
        powerpoint = DispatchEx("PowerPoint.Application")
        presentation = powerpoint.Presentations.Open(
            str(source_path.resolve()), ReadOnly=True, Untitled=False, WithWindow=False
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        presentation.SaveAs(str(target_path.resolve()), 32)
    except Exception as error:
        raise PowerPointUnavailableError() from error
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if powerpoint is not None:
            try:
                powerpoint.Quit()
            except Exception:
                pass
        if initialized:
            pythoncom.CoUninitialize()


def ingest_document(
    *, data_dir: Path, course_id: str, filename: str, stream: BinaryIO
) -> tuple[Document, list[Page]]:
    safe_filename = Path(filename).name
    extension = Path(safe_filename).suffix.lower()
    if not safe_filename or extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentTypeError()

    document_id = str(uuid4())
    upload_dir = data_dir / "uploads" / document_id
    original_path = upload_dir / safe_filename
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        size = _copy_stream(stream, original_path)
        if size == 0:
            raise EmptyDocumentError()

        processed_pdf_path: Path | None = None
        pdf_path = original_path
        if extension in {".ppt", ".pptx"}:
            processed_pdf_path = data_dir / "processed" / document_id / "converted.pdf"
            export_powerpoint_to_pdf(original_path, processed_pdf_path)
            pdf_path = processed_pdf_path

        pages = _render_pdf(
            data_dir=data_dir,
            document_id=document_id,
            pdf_path=pdf_path,
        )
        document = Document(
            id=document_id,
            course_id=course_id,
            title=Path(safe_filename).stem,
            original_filename=safe_filename,
            file_type=extension.removeprefix("."),
            original_path=original_path.relative_to(data_dir).as_posix(),
            processed_pdf_path=(
                processed_pdf_path.relative_to(data_dir).as_posix()
                if processed_pdf_path is not None
                else None
            ),
            page_count=len(pages),
        )
        return document, pages
    except Exception:
        for directory in (
            data_dir / "uploads" / document_id,
            data_dir / "processed" / document_id,
            data_dir / "previews" / document_id,
        ):
            shutil.rmtree(directory, ignore_errors=True)
        raise


def _copy_stream(stream: BinaryIO, destination: Path) -> int:
    total = 0
    with destination.open("wb") as output:
        while chunk := stream.read(1024 * 1024):
            output.write(chunk)
            total += len(chunk)
    return total


def _render_pdf(*, data_dir: Path, document_id: str, pdf_path: Path) -> list[Page]:
    preview_dir = data_dir / "previews" / document_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    pages: list[Page] = []

    try:
        # Opening from bytes avoids a lingering Windows file handle when PyMuPDF
        # rejects a corrupt upload, so the failed document can be cleaned up.
        with fitz.open(stream=pdf_path.read_bytes(), filetype="pdf") as pdf:
            if pdf.page_count == 0:
                raise InvalidDocumentError()
            for index, pdf_page in enumerate(pdf):
                page_number = index + 1
                preview_path = preview_dir / f"page-{page_number:04d}.png"
                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                pixmap.save(preview_path)
                pages.append(
                    Page(
                        document_id=document_id,
                        page_number=page_number,
                        extracted_text=pdf_page.get_text("text"),
                        preview_path=preview_path.relative_to(data_dir).as_posix(),
                    )
                )
    except InvalidDocumentError:
        raise
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError) as error:
        raise InvalidDocumentError() from error

    return pages
