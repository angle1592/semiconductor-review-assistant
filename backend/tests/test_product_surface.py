from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_source_has_no_removed_provider_integration():
    removed_provider = "co" + "dex"
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
                if removed_provider in file.read_text(encoding="utf-8-sig").lower():
                    offenders.append(str(file.relative_to(ROOT)))
    assert offenders == []


def test_windows_package_uses_only_shiyao_identity_and_supervises_worker():
    spec = (ROOT / "packaging" / "shiyao.spec").read_text(encoding="utf-8-sig")
    installer = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8-sig")
    start = (ROOT / "start.ps1").read_text(encoding="utf-8-sig")
    stop = (ROOT / "stop.ps1").read_text(encoding="utf-8-sig")

    assert 'name="Shiyao"' in spec
    assert '#define MyAppName "拾要"' in installer
    assert '#define MyAppExeName "Shiyao.exe"' in installer
    assert r"{localappdata}\Programs\Shiyao" in installer
    assert r"{localappdata}\Shiyao" in installer
    assert "-m', 'app.jobs.worker'" in start
    assert "worker.pid" in start
    assert "worker.pid" in stop
    assert "Start-Process -Verb RunAs" not in start
