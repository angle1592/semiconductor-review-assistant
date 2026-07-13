# Windows Launcher Lifecycle Design

## Goal

Make the local review assistant behave like a normal Windows desktop application: launching it again reopens the existing app instead of failing on port 8000, and the user can start it from a desktop shortcut without opening a terminal.

## Root cause

The current launcher starts `python -m app.runner` as an independent hidden process and waits for Enter. Closing the PowerShell window bypasses the launcher's cleanup block, so the server continues listening on port 8000. A later launch sees the listener and reports a conflict even though that listener is the healthy review assistant.

## Startup behavior

`start.ps1` treats the backend as a persistent local process:

1. Request `http://127.0.0.1:<port>/ready`.
2. If the response identifies a healthy review database, open the browser and exit successfully without creating another process.
3. If readiness fails but the port is occupied, stop with the existing conflict message because another application owns the port.
4. If the port is free, start the backend hidden, store its launcher PID and stop-signal path under `data/runtime`, wait for readiness, open the browser, and exit.

The script accepts `-Port`, `-RuntimeDir`, `-PythonPath`, and `-NoBrowser` so its lifecycle can be tested without touching production port 8000 or opening browser windows.

## Stop behavior

`stop.ps1` first uses the runtime PID and graceful stop signal. Before signaling or terminating any process, it checks that the command line contains this project's Python path and `-m app.runner`. If runtime metadata is absent, it may inspect the listening PID, but it still refuses to stop an unrelated process. Stale runtime files are removed after shutdown.

## Desktop shortcut

`install-shortcut.ps1` creates `半导体复习台.lnk` on the Windows desktop. The shortcut runs `start.ps1` through hidden PowerShell, so double-clicking only opens the browser. The installer accepts an alternate shortcut path for automated testing.

## Failure handling

- A healthy existing instance is reused.
- An unrelated listener is never terminated or reused.
- A backend that exits or never becomes ready is stopped and its runtime files are cleaned.
- Stopping without a running instance succeeds without changing other processes.
- Closing the browser does not stop the backend; this is intentional so the next launch is immediate.

## Verification

- An integration test starts on a random port, launches twice, confirms the PID is unchanged, stops the service, and confirms the port is released.
- A second test binds an unrelated listener and confirms startup refuses it.
- A shortcut test creates a temporary `.lnk` and verifies its target and arguments.
- Existing backend tests and static checks remain green.

