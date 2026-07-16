from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.sources.parse_cache import ParseCache, parse_cache_key
from app.sources.parsers import parse_source
from app.sources.parsers.contracts import ParsedSource


Parser = Callable[[Path, Path], ParsedSource]


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
