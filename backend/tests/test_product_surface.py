from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_source_has_no_codex_integration():
    checked = [
        ROOT / "backend" / "app",
        ROOT / "backend" / "pyproject.toml",
        ROOT / "setup.ps1",
        ROOT / "scripts" / "build-windows.ps1",
        ROOT / "packaging",
    ]
    offenders: list[str] = []
    for path in checked:
        files = path.rglob("*") if path.is_dir() else [path]
        for file in files:
            if file.is_file() and file.suffix.lower() in {".py", ".toml", ".ps1", ".spec"}:
                if "codex" in file.read_text(encoding="utf-8-sig").lower():
                    offenders.append(str(file.relative_to(ROOT)))
    assert offenders == []
