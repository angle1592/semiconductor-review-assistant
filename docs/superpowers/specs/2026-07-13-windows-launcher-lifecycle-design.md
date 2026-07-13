# Windows Launcher Lifecycle Design

## Goal

Make the local review assistant behave like a normal Windows desktop application: launching it again reopens the existing app instead of failing on port 8000, and the user can start it from a desktop shortcut without opening a terminal.

## Root cause

The current launcher starts `python -m app.runner` as an independent hidden process and waits for Enter. Closing the PowerShell window bypasses the launcher's cleanup block, so the server continues listening on port 8000. A later launch sees the listener and reports a conflict even though that listener is the healthy review assistant.

## Startup behavior

`start.ps1` treats the backend as a persistent local process:

1. Acquire a per-project, per-port Windows mutex so concurrent double-clicks cannot both start a process.
2. Request `http://127.0.0.1:<port>/ready` and require the review assistant's application and protocol markers.
3. If the response identifies a healthy review database, open the browser and exit successfully without creating another process.
4. If readiness fails but the port is occupied, stop with the existing conflict message because another application owns the port.
5. If the port is free, start the backend hidden, store its launcher PID and stop-signal path under `data/runtime`, wait for readiness, open the browser, and exit.

The script accepts `-Port`, `-RuntimeDir`, `-PythonPath`, and `-NoBrowser` so its lifecycle can be tested without touching production port 8000 or opening browser windows.

For one-version rollout compatibility, the old generic readiness payload is accepted only when the listener command line independently matches this project's exact Python path and `-m app.runner`. A generic response from any other process is rejected.

## Stop behavior

`stop.ps1` shares the launcher's mutex, derives termination authority from the process listening on the requested port, and checks that its command line contains this project's Python path and `-m app.runner`. Runtime PID metadata alone never authorizes process termination, so a stale or reused PID cannot stop another instance. Stale runtime files are removed after shutdown.

The backup service excludes `data/runtime` from export, deletion, and restore. Runtime entries found in backups created by an older build are ignored so live PID and locked log files cannot interfere with data restoration.

## Desktop shortcut

`install-shortcut.ps1` creates `半导体复习台.lnk` on the Windows desktop. The shortcut runs `start.ps1` through hidden PowerShell, so double-clicking only opens the browser. The installer accepts an alternate shortcut path for automated testing.

## Failure handling

- A healthy existing instance is reused.
- Concurrent launches are serialized and record the winning process.
- An unrelated listener is never terminated or reused.
- A generic `/ready` response without the application marker is not reused.
- A verified pre-marker instance is reused during upgrade.
- A backend that exits or never becomes ready is stopped and its runtime files are cleaned.
- Setup failures from Python, pip, npm, or the frontend build stop immediately instead of reporting success.
- Stopping without a running instance succeeds without changing other processes.
- Closing the browser does not stop the backend; this is intentional so the next launch is immediate.

## Verification

- An integration test starts on a random port, launches twice, confirms the PID is unchanged, stops the service, and confirms the port is released.
- A second test binds an unrelated listener and confirms startup refuses it.
- Concurrent launch and stale-PID tests cover lifecycle races and process identity.
- A shortcut test creates a temporary `.lnk` and verifies its target and arguments.
- Backup tests verify live runtime files are excluded and survive legacy archive restoration.
- Existing backend tests and static checks remain green.
