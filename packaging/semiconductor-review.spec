from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


root = Path(SPECPATH).parent
frontend_dist = root / "frontend" / "dist"
if not (frontend_dist / "index.html").is_file():
    raise SystemExit("frontend/dist is missing; run npm run build first")

hidden_imports = sorted(
    set(
        collect_submodules("keyring.backends")
        + collect_submodules("codex_cli_bin")
        + collect_submodules("openai_codex")
        + [
            "pythoncom",
            "pywintypes",
            "win32api",
            "win32com.client",
            "win32con",
            "win32gui",
            "win32process",
            "win32timezone",
        ]
    )
)
codex_runtime_data = collect_data_files("codex_cli_bin", include_py_files=True)

a = Analysis(
    [str(root / "packaging" / "desktop_entry.py")],
    pathex=[str(root / "backend")],
    binaries=[],
    datas=[(str(frontend_dist), "frontend/dist"), *codex_runtime_data],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SemiconductorReview",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SemiconductorReview",
)
