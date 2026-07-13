import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows launcher tests")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh.exe")


def _free_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _run_script(script: str, *arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    assert POWERSHELL is not None
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / script),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        timeout=40,
        check=False,
    )


def _launcher_arguments(port: int, runtime_dir: Path) -> tuple[str, ...]:
    return (
        "-Port",
        str(port),
        "-RuntimeDir",
        str(runtime_dir),
        "-PythonPath",
        sys.executable,
        "-NoBrowser",
    )


def _is_ready(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/ready", timeout=0.5) as response:
            return response.status == 200 and b'"database":"ok"' in response.read()
    except (OSError, URLError):
        return False


def test_launcher_reuses_running_instance_and_stopper_releases_port(tmp_path: Path):
    port = _free_port()
    runtime_dir = tmp_path / "runtime"
    env = os.environ.copy()
    env["SEMIREVIEW_DATA_DIR"] = str(tmp_path / "data")
    env["SEMIREVIEW_FRONTEND_DIST"] = str(PROJECT_ROOT / "frontend" / "dist")
    arguments = _launcher_arguments(port, runtime_dir)

    try:
        first = _run_script("start.ps1", *arguments, env=env)
        assert first.returncode == 0
        assert _is_ready(port)
        first_pid = (runtime_dir / "server.pid").read_text(encoding="utf-8").strip()

        second = _run_script("start.ps1", *arguments, env=env)
        assert second.returncode == 0
        assert (runtime_dir / "server.pid").read_text(encoding="utf-8").strip() == first_pid

        stopped = _run_script(
            "stop.ps1",
            "-Port",
            str(port),
            "-RuntimeDir",
            str(runtime_dir),
            "-PythonPath",
            sys.executable,
            env=env,
        )
        assert stopped.returncode == 0
        deadline = time.monotonic() + 5
        while _is_ready(port) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _is_ready(port)
        assert not (runtime_dir / "server.pid").exists()
    finally:
        if (PROJECT_ROOT / "stop.ps1").exists() and _is_ready(port):
            _run_script(
                "stop.ps1",
                "-Port",
                str(port),
                "-RuntimeDir",
                str(runtime_dir),
                "-PythonPath",
                sys.executable,
                env=env,
            )


def test_launcher_refuses_an_unrelated_listener(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    env = os.environ.copy()
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        port = int(unrelated.getsockname()[1])

        result = _run_script(
            "start.ps1",
            *_launcher_arguments(port, runtime_dir),
            env=env,
        )

        assert result.returncode != 0
        assert unrelated.getsockname()[1] == port
        assert not (runtime_dir / "server.pid").exists()


def test_shortcut_installer_creates_hidden_desktop_launcher(tmp_path: Path):
    shortcut_path = tmp_path / "半导体复习台.lnk"
    env = os.environ.copy()

    installed = _run_script(
        "install-shortcut.ps1",
        "-ShortcutPath",
        str(shortcut_path),
        "-StartScript",
        str(PROJECT_ROOT / "start.ps1"),
        env=env,
    )

    assert installed.returncode == 0
    assert shortcut_path.exists()
    env["TEST_SHORTCUT_PATH"] = str(shortcut_path)
    inspect_command = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:TEST_SHORTCUT_PATH);"
        "@{TargetPath=$s.TargetPath;Arguments=$s.Arguments;"
        "WorkingDirectory=$s.WorkingDirectory}|ConvertTo-Json -Compress"
    )
    inspected = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", inspect_command],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    details = json.loads(inspected.stdout)
    assert details["TargetPath"].lower().endswith("powershell.exe")
    assert "-WindowStyle Hidden" in details["Arguments"]
    assert str(PROJECT_ROOT / "start.ps1") in details["Arguments"]
    assert Path(details["WorkingDirectory"]).resolve() == PROJECT_ROOT.resolve()
