# 拾要 Phase 4：复习内容、掌握记录与 Windows 交付 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans only when the user explicitly asks to execute this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已确认重点转化为提纲、记忆卡、原题和 AI 题目，记录掌握情况，完善备份诊断，并交付完全更名、无 Codex、普通用户可运行的 Windows 应用“拾要”。

**Architecture:** 原题与生成内容分别持久化，生成任务复用 Phase 3 worker 和精确缓存。学习记录只描述用户主动复习的尝试与掌握度，不引入考试日期或日程。备份包含正式资料和数据库但排除密钥、缓存、日志；Windows 启动器监督 API 与 worker 两个子进程。

**Tech Stack:** FastAPI、SQLModel、SQLite、React 19、React Query、Vitest、Playwright、PyInstaller、Inno Setup、PowerShell 5.1/7。

---

## Preconditions

- [ ] Phase 3 exit gate 已通过，项目能导入资料并确认重点。
- [ ] durable worker、provider adapters、local exact cache 可复用于生成任务。
- [ ] Windows 构建在普通用户 PowerShell 中运行，不申请管理员权限。

## Task 1: Persist original questions and generate review artifacts

**Files:**
- Create: `backend/app/study/__init__.py`
- Create: `backend/app/study/models.py`
- Create: `backend/app/study/schemas.py`
- Create: `backend/app/study/repository.py`
- Create: `backend/app/study/prompts.py`
- Create: `backend/app/study/service.py`
- Create: `backend/app/study/worker_handler.py`
- Create: `backend/app/study/router.py`
- Create: `backend/tests/test_source_questions.py`
- Create: `backend/tests/test_generated_artifacts.py`
- Modify: `backend/app/analysis/worker_handler.py`
- Modify: `backend/app/jobs/worker.py`
- Modify: `backend/app/runtime/migrations.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing persistence and provenance tests**

The tests must distinguish source questions from generated material:

```python
QuestionOrigin = Literal["source", "ai_new", "ai_variant", "ai_error_cause"]
ArtifactKind = Literal["outline", "flashcard", "ai_new", "ai_variant", "ai_error_cause"]

class SourceQuestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id", index=True)
    document_id: int = Field(foreign_key="sourcedocument.id", index=True)
    question_text: str
    answer_text: str | None = None
    source_block_ids_json: str
    user_edited: bool = False

class GeneratedArtifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id", index=True)
    kind: str = Field(index=True)
    payload_json: str
    keypoint_ids_json: str
    source_question_ids_json: str = "[]"
    run_id: int | None = Field(default=None, foreign_key="analysisrun.id")
    prompt_hash: str
```

Assert that every generated item points to confirmed key points, source questions stay recognizable after user edits, AI answers never overwrite source answers, and deleting a source reports dependent original questions before execution.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_source_questions.py tests/test_generated_artifacts.py -q
Pop-Location
```

- [ ] **Step 3: Persist extracted questions from analysis batches**

Phase 3 batch output already carries `source_questions`. Validate question/answer evidence block IDs, deduplicate by document plus normalized question hash, and persist them separately from key-point candidates. Provide edit, archive, and restore APIs for source questions.

- [ ] **Step 4: Implement generation types through the durable worker**

Expose `POST /api/projects/{id}/artifacts` with an explicit `kind`, selected confirmed key-point IDs, optional source-question IDs, provider/model profile, and run prompt override. Reuse Phase 3 batching, retry, cancellation, cache key, prompt snapshot, and job polling.

Structured payloads are:

```python
class OutlinePayload(BaseModel):
    title: str
    sections: list[OutlineSection]

class FlashcardPayload(BaseModel):
    front: str
    back: str
    keypoint_ids: list[int]

class PracticeQuestionPayload(BaseModel):
    question: str
    answer: str
    explanation: str
    origin: Literal["ai_new", "ai_variant", "ai_error_cause"]
    source_question_ids: list[int]
    keypoint_ids: list[int]
```

Variant and error-cause generation requires at least one source question; return `SOURCE_QUESTION_REQUIRED` with an action to choose original questions otherwise.

- [ ] **Step 5: Add migration version 6, routes, and worker dispatch**

Register `/api/source-questions`, `/api/projects/{id}/artifacts`, and `/api/artifacts/{id}` routes. Worker dispatches `analysis` and `artifact_generation` job kinds through separate handlers and treats unknown kinds as terminal configuration errors.

- [ ] **Step 6: Run and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_source_questions.py tests/test_generated_artifacts.py tests/test_analysis_worker.py tests/test_job_worker.py -q
Pop-Location
git add backend/app/study backend/app/analysis/worker_handler.py backend/app/jobs/worker.py backend/app/runtime/migrations.py backend/app/main.py backend/tests/test_source_questions.py backend/tests/test_generated_artifacts.py
git diff --cached --check
git commit -m "feat: generate traceable review materials"
```

## Task 2: Record study attempts and mastery without scheduling

**Files:**
- Create: `backend/app/mastery/__init__.py`
- Create: `backend/app/mastery/models.py`
- Create: `backend/app/mastery/schemas.py`
- Create: `backend/app/mastery/service.py`
- Create: `backend/app/mastery/router.py`
- Create: `backend/tests/test_mastery_api.py`
- Modify: `backend/app/runtime/migrations.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing mastery behavior tests**

Use an explicit user rating, not an inferred exam schedule:

```python
MasteryLevel = Literal["unrated", "learning", "familiar", "mastered"]
StudyMode = Literal["outline", "flashcards", "source_questions", "ai_questions"]

class StudyAttempt(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id", index=True)
    mode: str
    item_type: str
    item_id: int
    response_json: str | None = None
    correct: bool | None = None
    self_rating: str | None = None
    created_at: datetime

class MasteryRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id", index=True)
    target_type: str
    target_id: int
    level: str = "unrated"
    last_attempt_at: datetime | None = None
```

Tests assert that rating changes update one record, attempts remain append-only, correctness is optional for outlines/flashcards, and no due date, exam date, streak, or daily assignment is created.

- [ ] **Step 2: Implement migration version 7 and APIs**

Add:

- `POST /api/projects/{id}/study-attempts`;
- `PUT /api/projects/{id}/mastery/{target_type}/{target_id}`;
- `GET /api/projects/{id}/mastery` with filters by level/type;
- `GET /api/projects/{id}/mastery/summary` with counts only.

Validate the target belongs to the same project. A project deletion cascades attempts and records; an artifact deletion deletes its mastery record but keeps an anonymized attempt count only if the product later needs analytics—v1 deletes both to keep semantics simple.

- [ ] **Step 3: Run and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_mastery_api.py tests/test_projects_api.py tests/test_migrations.py -q
Pop-Location
git add backend/app/mastery backend/app/runtime/migrations.py backend/app/main.py backend/tests/test_mastery_api.py
git diff --cached --check
git commit -m "feat: track review mastery"
```

## Task 3: Build on-demand review and mastery interfaces

**Files:**
- Create: `frontend/src/api/study.ts`
- Create: `frontend/src/api/mastery.ts`
- Create: `frontend/src/pages/project/ReviewContentPage.tsx`
- Create: `frontend/src/pages/project/StudySessionPage.tsx`
- Create: `frontend/src/pages/project/MasteryPage.tsx`
- Create: `frontend/src/components/ArtifactGenerator.tsx`
- Create: `frontend/src/components/OutlineReview.tsx`
- Create: `frontend/src/components/FlashcardReview.tsx`
- Create: `frontend/src/components/QuestionReview.tsx`
- Create: `frontend/src/components/MasteryControl.tsx`
- Create: `frontend/src/pages/project/ReviewContentPage.test.tsx`
- Create: `frontend/src/pages/project/StudySessionPage.test.tsx`
- Create: `frontend/src/pages/project/MasteryPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing user-flow tests**

Test that the user chooses a mode on demand, can select key points/original questions, sees prerequisites before generation, leaves and restores a running generation job, reviews outline/cards/questions, reveals answers intentionally, records correctness/self-rating, changes mastery, and filters mastery summaries.

Assert there is no exam-date form, daily schedule, due list, streak, or automatic next-session modal.

- [ ] **Step 2: Implement separate content-management and study views**

`ReviewContentPage` owns artifact generation, history, rename/regenerate/delete, provenance, and source jumps. `StudySessionPage` is distraction-light and receives a mode plus selected item IDs. `MasteryPage` presents level counts and item filters, not calendar projections.

All generation actions show provider/model, input scope, expected output, and cache status after completion. A regenerated artifact creates a new row and leaves the old row until the user deletes it.

- [ ] **Step 3: Implement accessible interactions and error messages**

Flashcards support keyboard reveal/next; question review does not send free-text answers to the AI automatically. Every disabled action includes the missing prerequisite. Provider errors reuse the Phase 2 action buttons; source/provenance links use the Phase 3 preview.

- [ ] **Step 4: Run and commit**

Run:

```powershell
Push-Location frontend
npm test -- ReviewContentPage.test.tsx StudySessionPage.test.tsx MasteryPage.test.tsx
npm run lint
npm run build
Pop-Location
git add frontend/src/api/study.ts frontend/src/api/mastery.ts frontend/src/pages/project/ReviewContentPage.tsx frontend/src/pages/project/StudySessionPage.tsx frontend/src/pages/project/MasteryPage.tsx frontend/src/components/ArtifactGenerator.tsx frontend/src/components/OutlineReview.tsx frontend/src/components/FlashcardReview.tsx frontend/src/components/QuestionReview.tsx frontend/src/components/MasteryControl.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/pages/project/ReviewContentPage.test.tsx frontend/src/pages/project/StudySessionPage.test.tsx frontend/src/pages/project/MasteryPage.test.tsx
git diff --cached --check
git commit -m "feat: add on-demand review sessions"
```

## Task 4: Harden backups, cache controls, diagnostics, and secret redaction

**Files:**
- Modify: `backend/app/backup/service.py`
- Modify: `backend/app/backup/router.py`
- Create: `backend/app/diagnostics/__init__.py`
- Create: `backend/app/diagnostics/service.py`
- Create: `backend/app/diagnostics/router.py`
- Create: `backend/tests/test_shiyao_backup.py`
- Create: `backend/tests/test_diagnostics.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.test.tsx`

- [ ] **Step 1: Write backup and leakage tests first**

Tests must prove:

- backup includes `shiyao.db`, original source files, preview assets required for restore, confirmed points, original questions, artifacts, attempts, and mastery;
- backup excludes provider secret store, `Runtime/parse-cache`, `Runtime/ai-cache`, model caches, worker leases, `Logs`, and existing `Backups`;
- diagnostics include app/version/path writability, redacted provider host/protocol, model capability result, task counts, cache counts/bytes, and recent public error codes;
- diagnostics exclude API keys, request headers, source text, evidence quotes, questions, answers, prompts, and generated payloads;
- restore rejects path traversal, duplicate paths, checksum mismatch, unsupported format version, and any manifest claiming secrets.

- [ ] **Step 2: Rename and version the backup format**

Use `format_version: 2`, `product: "shiyao"`, and a temporary directory prefix `shiyao-backup-`/`shiyao-restore-`. Restore is all-or-nothing: validate and stage first, close the engine, swap formal files, reopen, migrate, then report counts. On failure, keep the pre-restore formal data intact.

- [ ] **Step 3: Implement cache inspection and clearing**

Expose cache statistics and separate actions for parse cache and AI result cache. Require confirmation containing the reported bytes and clarify: “清理缓存不会删除资料、重点、题目、复习内容或掌握记录；下次可能重新解析或调用模型。”

- [ ] **Step 4: Implement downloadable diagnostics**

Diagnostic ZIP contains `summary.json` and redacted recent logs only. Centralize redaction for `Authorization`, `x-api-key`, `api_key`, known secret values, and URL credentials. Add an invariant test that seeds a unique canary key and private source phrase and scans every archive entry for both.

- [ ] **Step 5: Run and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_shiyao_backup.py tests/test_diagnostics.py -q
Pop-Location
Push-Location frontend
npm test -- SettingsPage.test.tsx
Pop-Location
git add backend/app/backup backend/app/diagnostics backend/app/main.py backend/tests/test_shiyao_backup.py backend/tests/test_diagnostics.py frontend/src/pages/SettingsPage.tsx frontend/src/pages/SettingsPage.test.tsx
git diff --cached --check
git commit -m "feat: secure backup and diagnostics"
```

## Task 5: Rebrand and supervise the Windows application

**Files:**
- Rename: `packaging/semiconductor-review.spec` → `packaging/shiyao.spec`
- Modify: `packaging/desktop_entry.py`
- Modify: `packaging/installer.iss`
- Modify: `scripts/build-windows.ps1`
- Modify: `scripts/build-installer.ps1`
- Modify: `scripts/prepare-release.ps1`
- Modify: `scripts/verify-frozen-app.ps1`
- Modify: `scripts/test-installed-app.ps1`
- Modify: `scripts/build-user-guide.py`
- Modify: `start.ps1`
- Modify: `stop.ps1`
- Modify: `setup.ps1`
- Modify: `install-shortcut.ps1`
- Modify: `backend/app/desktop/instance.py`
- Modify: `backend/app/desktop/launcher.py`
- Modify: `backend/app/desktop/windows_session.py`
- Modify: `backend/tests/test_desktop_launcher.py`
- Modify: `backend/tests/test_windows_launcher.py`
- Modify: `backend/tests/test_powershell_encoding.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Write launcher and packaging assertions before the rename**

Tests must assert product executable `Shiyao.exe`, process identity `shiyao`, ready marker `shiyao-ready`, app folder `Shiyao`, database `shiyao.db`, Start Menu/desktop shortcut “拾要”, and uninstall display name “拾要”. Assert build scripts contain no Codex install/download/runtime checks.

Add a process-tree test: launching starts exactly one desktop supervisor, one API child, and one worker child; a second launch focuses/reuses the existing instance; stop/uninstall terminates both children; stale PID files recover safely.

- [ ] **Step 2: Run packaging tests and confirm RED**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_launcher.py tests/test_windows_launcher.py tests/test_powershell_encoding.py -q
Pop-Location
```

- [ ] **Step 3: Rename PyInstaller and installer identity**

Use `git mv packaging/semiconductor-review.spec packaging/shiyao.spec`. The spec bundles frontend assets and backend runtime dependencies, but no `openai_codex`, `codex_cli_bin`, Codex binary, local Codex home, or Codex credentials. Output layout is `release/staging/Shiyao/Shiyao.exe`; installer output follows the project’s existing version convention with `Shiyao` identity.

- [ ] **Step 4: Remove all Codex build logic and supervise both services**

Delete `Install-CodexSdk`, PyPI Codex metadata downloads, wheel hashing, hidden imports, collection hooks, and runtime assertions. `desktop_entry.py`/launcher starts API and `python -m app.jobs.worker` using hidden child-process windows, records both PIDs, waits for API readiness, and opens the local UI. It must not call `Start-Process -Verb RunAs` or write machine-wide locations.

On shutdown, send graceful termination, wait with a bounded timeout, then terminate only verified child PIDs whose executable and parent identity match the instance record. Never kill by broad process name.

- [ ] **Step 5: Rename scripts, paths, markers, and user-facing copy**

Replace old product identifiers across scripts, packaging, desktop runtime, CI artifacts, user guide, shortcut names, and installer registry entries. Preserve PowerShell 5.1 compatibility and UTF-8 BOM in non-ASCII `.ps1` files. Do not touch `%LOCALAPPDATA%\SemiconductorReview`; new runtime paths point only to the approved Shiyao workspace/app directory.

- [ ] **Step 6: Run scans, tests, build, and commit**

Run:

```powershell
rg -n -i "codex|openai-codex|codex_cli_bin|SemiconductorReview|semiconductor-review|半导体课后复习" backend frontend packaging scripts .github README.md *.ps1
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_launcher.py tests/test_windows_launcher.py tests/test_powershell_encoding.py -q
Pop-Location
.\scripts\build-windows.ps1
.\scripts\verify-frozen-app.ps1
```

Expected: search has no runtime/build/product hits; only a deliberate release note stating the former product was replaced is allowed and must not suggest compatibility or migration. Tests and frozen-app verification pass without UAC.

Run:

```powershell
git add packaging scripts start.ps1 stop.ps1 setup.ps1 install-shortcut.ps1 backend/app/desktop backend/tests/test_desktop_launcher.py backend/tests/test_windows_launcher.py backend/tests/test_powershell_encoding.py .github/workflows/ci.yml
git diff --cached --check
git commit -m "build: package shiyao without codex"
```

## Task 6: Verify the complete product and release documentation

**Files:**
- Create: `backend/tests/test_shiyao_full_story.py`
- Create: `frontend/e2e/shiyao-full-story.spec.ts`
- Modify: `frontend/e2e/app.spec.ts`
- Modify: `README.md`
- Create: `docs/user-guide.md`
- Modify: `scripts/build-user-guide.py`
- Modify: `scripts/prepare-release.ps1`

- [ ] **Step 1: Add the complete backend story**

Use fixture documents and fake OpenAI-compatible/Anthropic servers to prove:

1. create project and project importance prompt;
2. configure and validate each protocol, fetch models, and manually add a model;
3. import all approved formats under complete/degraded rules;
4. analyze selected blocks and entire source set;
5. crash/restart worker, retry a failed batch, and observe exact cache hit;
6. edit/confirm key points and preserve original questions/answers;
7. generate outline, flashcards, new questions, variants, and error-cause questions;
8. record attempts and mastery;
9. create/validate/restore backup;
10. export diagnostics and prove canary secrets/content are absent.

- [ ] **Step 2: Add the complete Playwright story**

Verify onboarding hints, provider validation/model selection, upload warnings, source preview, analysis scope, progress reload, candidate confirmation, all four review modes, mastery editing, settings/cache controls, and actionable error buttons. Use stable fake services; do not consume a real API key in CI.

- [ ] **Step 3: Rewrite README and user guide for the shipped product**

Document the “拾要” positioning and subtitle, supported formats and Office limitation, third-party-only API setup, model discovery/manual fallback, capability probes, cache semantics, worker recovery, backups, privacy boundaries, non-admin install, troubleshooting actions, and how to fully delete new Shiyao data. Do not document Codex configuration or old-data migration.

- [ ] **Step 4: Run the complete source and dependency audit**

Run:

```powershell
rg -n -i "codex|openai-codex|codex_cli_bin|SemiconductorReview|semiconductor-review|半导体课后复习|考试日期|每日计划" --glob "!docs/superpowers/specs/**" --glob "!docs/superpowers/plans/**" .
Push-Location backend
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check app tests
Pop-Location
Push-Location frontend
npm audit --omit=dev
Pop-Location
```

Expected: the product scan is clean except explicit migration-free release history; dependency checks report no broken runtime dependencies. Address audit findings according to the repository’s existing severity policy before release.

- [ ] **Step 5: Run the final automated release gate**

Run:

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('shiyao-release-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $base
Pop-Location
Push-Location frontend
npm test
npm run lint
npm run build
npm run test:e2e
Pop-Location
.\scripts\build-windows.ps1
.\scripts\verify-frozen-app.ps1
.\scripts\build-installer.ps1
.\scripts\test-installed-app.ps1
.\scripts\prepare-release.ps1
```

Expected: all tests pass, frozen app and installed app complete the full story, neither requests elevation, and release artifacts use Shiyao identity.

- [ ] **Step 6: Perform the ordinary-user manual acceptance pass**

On a standard non-admin Windows account:

- launch from desktop and Start Menu;
- complete first provider setup using a disposable third-party key;
- validate URL/key/model and run text/structured/vision probes;
- import a visual PDF and an Office document;
- finish selected-range analysis, confirm points, generate all review modes, and record mastery;
- restart during a multi-batch job and verify recovery;
- clear caches and prove formal data remains;
- back up, uninstall, reinstall, restore, and verify data;
- confirm Task Manager/process inspection shows no orphan worker and no UAC dialog.

Record app version, commit SHA, installer SHA-256, test account type, and pass/fail results in the release notes.

- [ ] **Step 7: Commit final verification assets**

Run:

```powershell
git add backend/tests/test_shiyao_full_story.py frontend/e2e/shiyao-full-story.spec.ts frontend/e2e/app.spec.ts README.md docs/user-guide.md scripts/build-user-guide.py scripts/prepare-release.ps1
git diff --cached --check
git commit -m "test: verify shiyao release story"
```

## Phase 4 exit criteria

- [ ] 提纲、记忆卡、原题和三类 AI 题目均可按需创建并追溯来源。
- [ ] 掌握记录可用，产品没有考试日期、日程或每日任务机制。
- [ ] 备份能恢复全部正式数据，密钥、缓存、日志和任务租约不进入备份。
- [ ] 诊断包不包含密钥、资料正文、题目答案、提示词或生成正文。
- [ ] 源码、依赖、构建、安装包、设置和文档都没有 Codex 接入。
- [ ] 所有产品标识、可执行文件、目录、快捷方式和安装信息均为“拾要”/`Shiyao`。
- [ ] 普通用户安装、启动、分析、重启恢复、卸载全程不触发 UAC，且无孤儿 worker。
- [ ] 全量后端、前端、E2E、冻结应用和安装包验收通过。
