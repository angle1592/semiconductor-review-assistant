from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from app.sources.parsers.contracts import ParsedBlock, ParsedSource


def parse_cache_key(file_sha256: str, parser_version: str) -> str:
    raw = f"{file_sha256}\0{parser_version}".encode()
    return hashlib.sha256(raw).hexdigest()


def _asset_paths(parsed: ParsedSource) -> set[str]:
    paths = set(parsed.render_paths)
    paths.update(block.asset_path for block in parsed.blocks if block.asset_path)
    return paths


def _inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


class ParseCache:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _entry(self, key: str) -> Path:
        return self.root / key[:2] / key

    def _discard(self, entry: Path) -> None:
        if entry.exists():
            shutil.rmtree(entry)

    def load(self, key: str) -> ParsedSource | None:
        entry = self._entry(key)
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            self._discard(entry)
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            blocks = tuple(
                ParsedBlock(
                    locator=item["locator"],
                    kind=item["kind"],
                    text=item["text"],
                    page_number=item["page_number"],
                    heading_path=tuple(item["heading_path"]),
                    asset_path=item.get("asset_path"),
                )
                for item in manifest["blocks"]
            )
            parsed = ParsedSource(
                page_count=manifest["page_count"],
                blocks=blocks,
                warnings=tuple(manifest["warnings"]),
                render_paths=tuple(manifest["render_paths"]),
            )
            if any(not _inside(entry, relative).is_file() for relative in _asset_paths(parsed)):
                raise ValueError("cache asset is missing")
            return parsed
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._discard(entry)
            return None

    def store(
        self,
        key: str,
        parser_version: str,
        parsed: ParsedSource,
        output_dir: Path,
    ) -> None:
        entry = self._entry(key)
        if entry.exists():
            return
        entry.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{key}-", dir=entry.parent))
        try:
            for relative in _asset_paths(parsed):
                source = _inside(output_dir, relative)
                target = _inside(temporary, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            manifest = {
                "parser_version": parser_version,
                "page_count": parsed.page_count,
                "blocks": [asdict(block) for block in parsed.blocks],
                "warnings": list(parsed.warnings),
                "render_paths": list(parsed.render_paths),
                "created_at": datetime.now(UTC).isoformat(),
            }
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, entry)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def materialize(self, key: str, parsed: ParsedSource, output_dir: Path) -> None:
        entry = self._entry(key)
        output_dir.mkdir(parents=True, exist_ok=True)
        for relative in _asset_paths(parsed):
            source = _inside(entry, relative)
            target = _inside(output_dir, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def clear(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
