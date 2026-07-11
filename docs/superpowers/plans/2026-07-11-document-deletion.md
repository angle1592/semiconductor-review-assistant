# Document Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a permanent, confirmed delete action for imported course documents without deleting learning history.

**Architecture:** FastAPI exposes a REST DELETE endpoint in the existing content feature. The content service removes only the document-scoped upload, processed, and preview directories; React Query invokes the endpoint and invalidates the document list.

**Tech Stack:** Python, FastAPI, SQLModel, SQLite, React, TypeScript, TanStack Query, Vitest

---

### Task 1: Backend deletion contract

**Files:**
- Modify: `backend/tests/test_content_api.py`
- Modify: `backend/app/content/service.py`
- Modify: `backend/app/content/router.py`

- [ ] Add an integration test that uploads a PDF, creates a lesson referencing one page, calls `DELETE /api/documents/{id}`, and asserts HTTP 204, document/page removal, directory removal, and lesson preservation.
- [ ] Run `pytest backend/tests/test_content_api.py -q` and verify the new test fails with HTTP 405.
- [ ] Add `delete_document_files(data_dir, document_id)` that resolves and removes only `uploads/{id}`, `processed/{id}`, and `previews/{id}`.
- [ ] Add the DELETE route, delete child `Page` rows before the `Document`, commit, and return HTTP 204.
- [ ] Re-run the content tests and verify they pass.

### Task 2: Frontend delete control

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/CourseDetailPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/pages/CourseDetailPage.test.tsx`

- [ ] Add a component test that renders an imported document, clicks “删除课件”, accepts confirmation, and expects the API delete method plus document-query invalidation.
- [ ] Run the focused Vitest test and verify it fails because the control/API method is absent.
- [ ] Add `api.deleteDocument(documentId)` using HTTP DELETE.
- [ ] Add a `useMutation`, confirmation prompt, pending state, success notice, query invalidation, and error notice to the course page.
- [ ] Add a compact danger-button style that follows the existing card layout and remains usable on narrow screens.
- [ ] Re-run the focused frontend test and verify it passes.

### Task 3: Verification

**Files:**
- Verify only

- [ ] Run all backend tests and Ruff checks.
- [ ] Run frontend unit tests, ESLint, and production build.
- [ ] Start the app and smoke-test document deletion through the REST endpoint and browser UI.
- [ ] Commit only deletion-related source, tests, and documentation; preserve unrelated workspace changes.

