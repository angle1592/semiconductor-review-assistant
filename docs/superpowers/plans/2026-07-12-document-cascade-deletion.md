# Document Cascade Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make document deletion remove every lesson, generated item, answer, and schedule derived from that document without deleting unrelated questions in mixed review sessions.

**Architecture:** A focused content deletion service receives the SQLModel session and page IDs, calculates affected lessons and questions, then deletes or rewrites dependent records within the existing request transaction. The DELETE endpoint and React Query mutation stay unchanged; only the confirmation text changes to describe the permanent cascade.

**Tech Stack:** Python, FastAPI, SQLModel, SQLite, React, TypeScript, TanStack Query, Pytest, Vitest, Playwright

---

### Task 1: Cascade deletion transaction

**Files:**
- Create: `backend/app/content/deletion.py`
- Modify: `backend/app/content/router.py`
- Modify: `backend/tests/test_content_ingestion.py`

- [ ] Replace the existing preservation test with a failing integration test that creates an affected lesson/question/attempt, an unrelated lesson/question/attempt, and one mixed review session; after DELETE, assert all affected records are gone while the mixed session retains only the unrelated question.
- [ ] Run `pytest backend/tests/test_content_ingestion.py::test_delete_document_cascades_learning_data_without_harming_other_sources -q` and verify it fails because the affected lesson still exists.
- [ ] Add `cascade_document_learning_data(session, page_ids)` that loads JSON ID lists, finds lessons intersecting the page IDs, deletes their attempts/questions/knowledge points, trims review-session question lists, deletes empty sessions, and deletes the affected lessons.
- [ ] Call the cascade service before deleting `Page` and `Document` records, then commit once in the existing DELETE route.
- [ ] Re-run the focused and complete content-ingestion tests and verify they pass.

### Task 2: Destructive confirmation copy

**Files:**
- Modify: `frontend/src/pages/CourseDetailPage.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/e2e/app.spec.ts`

- [ ] Change the component test expectation first so confirmation must mention that related lessons, questions, answers, and review history are deleted; run the focused Vitest test and verify it fails on the old preservation message.
- [ ] Replace the confirmation copy with: `相关课次、题目、答案和复习记录也会一并删除，此操作无法撤销。`
- [ ] Update the Playwright dialog assertion to match the new warning.
- [ ] Run frontend unit tests, ESLint, production build, and Playwright tests.

### Task 3: Final verification and integration

**Files:**
- Verify only

- [ ] Run all backend tests, Ruff checks, and Ruff formatting checks.
- [ ] Verify the main worktree retains unrelated README and `%SystemDrive%` changes.
- [ ] Commit only cascade-related files, merge the isolated branch locally, rerun all tests on main, and remove the isolated worktree.

