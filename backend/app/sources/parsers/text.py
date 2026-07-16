import re
from pathlib import Path

from app.sources.parsers.contracts import ParsedBlock, ParsedSource


def _decode(source: Path) -> str:
    content = source.read_bytes()
    if content.startswith(b"\xef\xbb\xbf"):
        return content.decode("utf-8-sig")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("gb18030")


def parse_text(source: Path, output_dir: Path) -> ParsedSource:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = source.suffix.lower() == ".md"
    heading_path: list[str] = []
    blocks: list[ParsedBlock] = []

    for line_number, raw_line in enumerate(_decode(source).splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        kind = "paragraph"
        text = line
        if markdown:
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            listing = re.match(r"^(?:[-*+] |\d+[.)] )(.+)$", line)
            if heading:
                level = len(heading.group(1))
                text = heading.group(2).strip()
                heading_path = heading_path[: level - 1]
                heading_path.append(text)
                kind = "heading"
            elif listing:
                text = listing.group(1).strip()
                kind = "list"
        blocks.append(
            ParsedBlock(
                locator=f"line:{line_number}",
                kind=kind,
                text=text,
                page_number=None,
                heading_path=tuple(heading_path),
            )
        )

    return ParsedSource(None, tuple(blocks), (), ())
