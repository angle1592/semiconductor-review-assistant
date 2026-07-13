# Course Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe course deletion that removes the course's complete learning history and local files from the course list.

**Architecture:** Extend the existing deletion service with a course-scoped cascade and expose it through `DELETE /api/courses/{course_id}`. Add a React Query mutation and an independent card action on the course list. Reuse the document deletion rules so mixed review sessions retain questions from other courses.

**Tech Stack:** FastAPI, SQLModel, SQLite, React, TypeScript, TanStack Query, Vitest, Playwright

---

### Task 1: Backend course cascade

**Files:**
- Modify: `backend/tests/test_courses_api.py`
- Modify: `backend/app/content/deletion.py`
- Modify: `backend/app/courses/router.py`

- [ ] Write an integration test that creates two courses with documents, pages, Notebook imports, lessons, questions, attempts, and a mixed review session.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_courses_api.py -q` and verify the new test fails with HTTP 405.
- [ ] Add a course-scoped deletion service and `DELETE /api/courses/{course_id}` returning 204.
- [ ] Verify the test passes and missing courses return the standard 404 response.

### Task 2: Course-list delete interaction

**Files:**
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/CoursesPage.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Write a UI test that confirms the destructive warning, sends DELETE, removes the course, and shows success feedback.
- [ ] Run `npm test -- --run src/App.test.tsx` from `frontend` and verify the new test fails because no delete button exists.
- [ ] Add `api.deleteCourse`, a React Query delete mutation, a separate card delete button, confirmation, and user-facing success/error feedback.
- [ ] Verify the focused UI test passes.

### Task 3: End-to-end verification

**Files:**
- Modify: `frontend/e2e/app.spec.ts`

- [ ] Add a Playwright flow that creates a disposable course, deletes it from the list, and verifies it disappears.
- [ ] Run the complete backend tests, Ruff, frontend tests, ESLint, build, and Playwright suite.
- [ ] Commit the implementation after every verification is green.

