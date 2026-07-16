from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedBlock:
    locator: str
    kind: str
    text: str
    page_number: int | None
    heading_path: tuple[str, ...]
    asset_path: str | None = None


@dataclass(frozen=True)
class ParsedSource:
    page_count: int | None
    blocks: tuple[ParsedBlock, ...]
    warnings: tuple[str, ...]
    render_paths: tuple[str, ...]
