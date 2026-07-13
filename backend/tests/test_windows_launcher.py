import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def _script_command(script: str, *arguments: str) -> list[str]:
    assert POWERSHELL is not None
    return [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PROJECT_ROOT / script),
        *arguments,
    ]


def _run_script(script: str, *arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    with tempfile.TemporaryFile() as output:
        completed = subprocess.run(
            _script_command(script, *arguments),
            cwd=PROJECT_ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=40,
            check=False,
        )
        output.seek(0)
        captured = output.read()
    if completed.returncode != 0:
        print(captured.decode(errors="replace"), file=sys.stderr)
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        stdout=captured,
        stderr=None,
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


def _launcher_environment(tmp_path: Path) -> dict[str, str]:
    frontend_dist = tmp_path / "frontend-dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    env = os.environ.copy()
    env["SEMIREVIEW_DATA_DIR"] = str(tmp_path / "data")
    env["SEMIREVIEW_FRONTEND_DIST"] = str(frontend_dist)
    return env


def _is_ready(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/ready", timeout=0.5) as response:
            return response.status == 200 and b'"database":"ok"' in response.read()
    except (OSError, URLError):
        return False


def _listener_pid(port: int) -> int:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 5 and fields[1].endswith(f":{port}") and fields[3] == "LISTENING":
            return int(fields[4])
    raise AssertionError(f"No listener found on port {port}")


def _parent_pid(process_id: int) -> int:
    assert POWERSHELL is not None
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={process_id}').ParentProcessId",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return int(result.stdout.strip())


def test_launcher_reuses_running_instance_and_stopper_releases_port(tmp_path: Path):
    port = _free_port()
    runtime_dir = tmp_path / "runtime"
    env = _launcher_environment(tmp_path)
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
        with pytest.raises(AssertionError, match="No listener"):
            _listener_pid(port)
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


def test_concurrent_launches_record_the_winning_server_process(tmp_path: Path):
    port = _free_port()
    runtime_dir = tmp_path / "runtime"
    env = _launcher_environment(tmp_path)
    command = _script_command("start.ps1", *_launcher_arguments(port, runtime_dir))

    try:
        launch_options = {
            "cwd": PROJECT_ROOT,
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        first = subprocess.Popen(command, **launch_options)
        second = subprocess.Popen(command, **launch_options)

        assert first.wait(timeout=60) == 0
        assert second.wait(timeout=60) == 0
        listener_pid = _listener_pid(port)
        recorded_pid = int((runtime_dir / "server.pid").read_text(encoding="ascii"))
        assert recorded_pid == _parent_pid(listener_pid)
    finally:
        if _is_ready(port):
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


def test_launcher_refuses_a_generic_ready_response_without_app_marker(tmp_path: Path):
    class GenericReadyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            content = b'{"status":"ok","checks":{"database":"ok"}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            return

    runtime_dir = tmp_path / "runtime"
    env = os.environ.copy()
    with ThreadingHTTPServer(("127.0.0.1", 0), GenericReadyHandler) as unrelated:
        port = int(unrelated.server_address[1])
        thread = threading.Thread(target=unrelated.serve_forever, daemon=True)
        thread.start()
        try:
            result = _run_script(
                "start.ps1",
                *_launcher_arguments(port, runtime_dir),
                env=env,
            )
        finally:
            unrelated.shutdown()
            thread.join(timeout=5)

    assert result.returncode != 0
    assert not (runtime_dir / "server.pid").exists()


def test_launcher_reuses_a_verified_legacy_runner_without_app_marker(tmp_path: Path):
    port = _free_port()
    runtime_dir = tmp_path / "runtime"
    env = os.environ.copy()
    legacy_code = """
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        content = b'{"status":"ok","checks":{"database":"ok"}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return

ThreadingHTTPServer(("127.0.0.1", int(sys.argv[-1])), Handler).serve_forever()
"""
    legacy = subprocess.Popen(
        [sys.executable, "-c", legacy_code, "-m", "app.runner", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        deadline = time.monotonic() + 10
        while not _is_ready(port) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _is_ready(port)

        result = _run_script(
            "start.ps1",
            *_launcher_arguments(port, runtime_dir),
            env=env,
        )

        assert result.returncode == 0
        assert _is_ready(port)
        assert not (runtime_dir / "server.pid").exists()
    finally:
        subprocess.run(
            ["taskkill", "/PID", str(legacy.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )


def test_stopper_does_not_kill_a_runner_referenced_by_stale_metadata(tmp_path: Path):
    live_port = _free_port()
    unused_port = _free_port()
    live_runtime = tmp_path / "live-runtime"
    stale_runtime = tmp_path / "stale-runtime"
    env = _launcher_environment(tmp_path)

    try:
        started = _run_script(
            "start.ps1",
            *_launcher_arguments(live_port, live_runtime),
            env=env,
        )
        assert started.returncode == 0
        assert _is_ready(live_port)
        stale_runtime.mkdir(parents=True)
        (stale_runtime / "server.pid").write_text(
            str(_listener_pid(live_port)),
            encoding="ascii",
        )

        stopped = _run_script(
            "stop.ps1",
            "-Port",
            str(unused_port),
            "-RuntimeDir",
            str(stale_runtime),
            "-PythonPath",
            sys.executable,
            env=env,
        )

        assert stopped.returncode == 0
        assert _is_ready(live_port)
        assert not (stale_runtime / "server.pid").exists()
    finally:
        if _is_ready(live_port):
            _run_script(
                "stop.ps1",
                "-Port",
                str(live_port),
                "-RuntimeDir",
                str(live_runtime),
                "-PythonPath",
                sys.executable,
                env=env,
            )


def test_shortcut_installer_creates_hidden_desktop_launcher(tmp_path: Path):
    shortcut_path = tmp_path / "folder with spaces" / "半导体复习台.lnk"
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
