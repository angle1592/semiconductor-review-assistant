import json
from pathlib import Path

from app.sources.parse_cache import ParseCache, parse_cache_key
from app.sources.parsers.contracts import ParsedBlock, ParsedSource
from app.sources.service import SourceParsingService


def _parsed_with_asset(output_dir: Path, text: str = "cached content") -> ParsedSource:
    asset = output_dir / "pages" / "page-0001.png"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"preview")
    return ParsedSource(
        page_count=1,
        blocks=(ParsedBlock("page:1:block:1", "paragraph", text, 1, ()),),
        warnings=(),
        render_paths=("pages/page-0001.png",),
    )


def test_second_identical_parse_hits_cache_without_parser_call(tmp_path: Path):
    calls = 0

    def parser(_source: Path, output_dir: Path) -> ParsedSource:
        nonlocal calls
        calls += 1
        return _parsed_with_asset(output_dir)

    source = tmp_path / "material.txt"
    source.write_text("same material", encoding="utf-8")
    service = SourceParsingService(ParseCache(tmp_path / "Runtime" / "parse-cache"), {".txt": parser})

    first = service.parse(source, "file-sha", "parser-v1", tmp_path / "first")
    second = service.parse(source, "file-sha", "parser-v1", tmp_path / "second")

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert calls == 1
    assert second.parsed == first.parsed
    assert (tmp_path / "second" / "pages" / "page-0001.png").read_bytes() == b"preview"


def test_parser_version_change_misses_cache(tmp_path: Path):
    calls = 0

    def parser(_source: Path, output_dir: Path) -> ParsedSource:
        nonlocal calls
        calls += 1
        return _parsed_with_asset(output_dir, f"call-{calls}")

    source = tmp_path / "material.txt"
    source.write_text("same material", encoding="utf-8")
    service = SourceParsingService(ParseCache(tmp_path / "parse-cache"), {".txt": parser})

    service.parse(source, "file-sha", "parser-v1", tmp_path / "v1")
    changed = service.parse(source, "file-sha", "parser-v2", tmp_path / "v2")

    assert calls == 2
    assert changed.cache_status == "miss"
    assert changed.parsed.blocks[0].text == "call-2"


def test_incomplete_cache_manifest_is_discarded(tmp_path: Path):
    cache = ParseCache(tmp_path / "parse-cache")
    key = parse_cache_key("file-sha", "parser-v1")
    entry = cache.root / key[:2] / key
    entry.mkdir(parents=True)
    (entry / "manifest.json").write_text(
        json.dumps(
            {
                "parser_version": "parser-v1",
                "page_count": 1,
                "blocks": [],
                "warnings": [],
                "render_paths": ["pages/missing.png"],
                "created_at": "2026-07-16T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    assert cache.load(key) is None
    assert not entry.exists()


def test_clearing_parse_cache_preserves_formal_database(tmp_path: Path):
    database = tmp_path / "Data" / "shiyao.db"
    database.parent.mkdir()
    database.write_bytes(b"formal rows")
    cache = ParseCache(tmp_path / "Runtime" / "parse-cache")
    entry = cache.root / "aa" / "cache-entry"
    entry.mkdir(parents=True)
    (entry / "manifest.json").write_text("{}", encoding="utf-8")

    cache.clear()

    assert database.read_bytes() == b"formal rows"
    assert cache.root.is_dir()
    assert list(cache.root.iterdir()) == []
