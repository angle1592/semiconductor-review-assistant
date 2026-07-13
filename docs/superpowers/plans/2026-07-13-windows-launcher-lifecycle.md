# Windows Launcher Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse a healthy running review assistant, provide a safe stop command, and install a no-terminal Windows desktop shortcut.

**Architecture:** Keep the FastAPI runner unchanged and move lifecycle ownership into PowerShell scripts. The launcher records a PID and fixed stop-signal path, the stopper verifies process identity before acting, and the shortcut invokes the launcher hidden. Tests use a random port and isolated runtime/data directories.

**Tech Stack:** PowerShell 5.1+, Windows Script Host shortcuts, Python subprocess integration tests, FastAPI readiness endpoint

---

### Task 1: Reusable persistent launcher and safe stopper

**Files:**
- Create: `backend/tests/test_windows_launcher.py`
- Modify: `start.ps1`
- Create: `stop.ps1`

- [ ] Write a Windows-only integration test that invokes `start.ps1` twice on a random port with `-NoBrowser`, verifies `server.pid` is unchanged, invokes `stop.ps1`, and verifies readiness disappears.
- [ ] Write a second test that owns a random port with an unrelated socket and verifies `start.ps1` exits nonzero without disturbing the socket.
- [ ] Run `python -m pytest tests/test_windows_launcher.py -q` and verify both tests fail because the launcher parameters and stopper do not exist.
- [ ] Replace the Enter-bound launcher lifecycle with readiness reuse, runtime metadata, detached startup, and startup cleanup.
- [ ] Implement `stop.ps1` with graceful signaling and verified-process fallback.
- [ ] Run the focused integration tests and verify they pass.

### Task 2: Desktop shortcut installer

**Files:**
- Modify: `backend/tests/test_windows_launcher.py`
- Create: `install-shortcut.ps1`

- [ ] Add a test that installs a shortcut to a temporary path and reads it through `WScript.Shell`.
- [ ] Run the focused shortcut test and verify it fails because the installer does not exist.
- [ ] Implement the installer with a desktop default, hidden PowerShell arguments, working directory, description, and icon.
- [ ] Run all launcher tests and verify they pass.

### Task 3: Full verification and installation

**Files:**
- Modify: `docs/superpowers/plans/2026-07-13-windows-launcher-lifecycle.md`

- [ ] Run the complete backend test suite and Ruff.
- [ ] Run a manual lifecycle check on an unused port and confirm no process remains after `stop.ps1`.
- [ ] Mark the plan complete and commit the implementation.
- [ ] Merge to `main`, run `install-shortcut.ps1`, and verify the desktop shortcut reopens a single healthy instance on port 8000.

