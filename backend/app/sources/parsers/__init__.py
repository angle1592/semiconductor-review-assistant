from pathlib import Path
import tempfile

from app.sources.parsers.contracts import ParsedSource
from app.sources.parsers.docx import parse_docx
from app.sources.parsers.office import convert_legacy_office
from app.sources.parsers.pdf import parse_pdf
from app.sources.parsers.pptx import parse_pptx
from app.sources.parsers.text import parse_text


def parse_source(source: Path, output_dir: Path) -> ParsedSource:
    extension = source.suffix.lower()
    if extension == ".pdf":
        return parse_pdf(source, output_dir)
    if extension == ".docx":
        return parse_docx(source, output_dir)
    if extension == ".pptx":
        return parse_pptx(source, output_dir)
    if extension in {".txt", ".md"}:
        return parse_text(source, output_dir)
    if extension in {".doc", ".ppt"}:
        with tempfile.TemporaryDirectory(prefix="shiyao-office-") as temporary:
            converted = convert_legacy_office(source, Path(temporary))
            return parse_source(converted, output_dir)
    raise ValueError(f"Unsupported source extension: {extension}")
