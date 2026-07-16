from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.sources.parsers.contracts import ParsedBlock, ParsedSource


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    if not style_name.lower().startswith("heading"):
        return None
    try:
        return max(1, int(style_name.split()[-1]))
    except ValueError:
        return 1


def _image_extension(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(content_type, ".bin")


def parse_docx(source: Path, output_dir: Path) -> ParsedSource:
    output_dir.mkdir(parents=True, exist_ok=True)
    document: DocumentObject = Document(source)
    blocks: list[ParsedBlock] = []
    heading_path: list[str] = []
    image_index = 0

    for body_index, element in enumerate(document.element.body.iterchildren(), start=1):
        if element.tag == qn("w:p"):
            paragraph = Paragraph(element, document)
            text = paragraph.text.strip()
            level = _heading_level(paragraph)
            if text:
                if level is not None:
                    heading_path = heading_path[: level - 1]
                    heading_path.append(text)
                    kind = "heading"
                else:
                    kind = "paragraph"
                blocks.append(
                    ParsedBlock(
                        locator=f"body:{body_index}:paragraph",
                        kind=kind,
                        text=text,
                        page_number=None,
                        heading_path=tuple(heading_path),
                    )
                )
            for blip_index, blip in enumerate(element.xpath(".//a:blip"), start=1):
                relationship_id = blip.get(qn("r:embed"))
                if not relationship_id:
                    continue
                part = document.part.related_parts[relationship_id]
                image_index += 1
                extension = _image_extension(part.content_type)
                relative = f"images/image-{image_index:04d}{extension}"
                target = output_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(part.blob)
                blocks.append(
                    ParsedBlock(
                        locator=f"body:{body_index}:image:{blip_index}",
                        kind="image",
                        text="",
                        page_number=None,
                        heading_path=tuple(heading_path),
                        asset_path=relative,
                    )
                )
        elif element.tag == qn("w:tbl"):
            table = Table(element, document)
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            blocks.append(
                ParsedBlock(
                    locator=f"body:{body_index}:table",
                    kind="table",
                    text="\n".join(rows),
                    page_number=None,
                    heading_path=tuple(heading_path),
                )
            )

    return ParsedSource(None, tuple(blocks), (), ())
