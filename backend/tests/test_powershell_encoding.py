from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IGNORED_DIRECTORIES = {
    ".git",
    ".worktrees",
    ".venv",
    ".build-venv",
    "build",
    "node_modules",
    "release",
}


def test_non_ascii_powershell_scripts_use_utf8_bom() -> None:
    invalid: list[str] = []
    for script in PROJECT_ROOT.rglob("*.ps1"):
        relative = script.relative_to(PROJECT_ROOT)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        content = script.read_bytes()
        decoded = content.decode("utf-8-sig")
        if any(ord(character) > 127 for character in decoded) and not content.startswith(
            b"\xef\xbb\xbf"
        ):
            invalid.append(relative.as_posix())

    assert invalid == [], (
        "Windows PowerShell 5.1 misreads non-ASCII UTF-8 scripts without a BOM: "
        + ", ".join(sorted(invalid))
    )
