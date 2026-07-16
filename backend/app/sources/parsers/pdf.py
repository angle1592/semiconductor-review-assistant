from pathlib import Path

import fitz

from app.sources.parsers.contracts import ParsedBlock, ParsedSource


def parse_pdf(source: Path, output_dir: Path) -> ParsedSource:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    blocks: list[ParsedBlock] = []
    render_paths: list[str] = []

    with fitz.open(source) as document:
        if document.needs_pass:
            raise ValueError("PDF is encrypted")
        for page_index, page in enumerate(document, start=1):
            page_blocks = sorted(page.get_text("blocks"), key=lambda item: (item[1], item[0]))
            text_index = 0
            for raw in page_blocks:
                text = str(raw[4]).strip()
                if not text:
                    continue
                text_index += 1
                blocks.append(
                    ParsedBlock(
                        locator=f"page:{page_index}:block:{text_index}",
                        kind="paragraph",
                        text=text,
                        page_number=page_index,
                        heading_path=(),
                    )
                )
            relative = f"pages/page-{page_index:04d}.png"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pixmap.save(output_dir / relative)
            render_paths.append(relative)
        page_count = document.page_count

    return ParsedSource(page_count, tuple(blocks), (), tuple(render_paths))
