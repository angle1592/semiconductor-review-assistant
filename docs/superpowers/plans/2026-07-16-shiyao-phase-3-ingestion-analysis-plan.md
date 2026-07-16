# 拾要 Phase 3：资料导入、分析任务与重点确认 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans only when the user explicitly asks to execute this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Phase 2 的第三方 AI 接入之上，完成多格式资料导入、稳定内容块、可恢复分析任务、分层缓存，以及“AI 提候选—用户确认重点”的完整主流程。

**Architecture:** 原文件与渲染结果保存在项目数据目录，SQLite 保存资料、内容块、分析批次、重点和任务状态。API 进程只创建任务并提供查询，独立 worker 领取 SQLite 队列并分批调用模型；每批结果先落候选重点，只有用户确认后才成为正式重点。

**Tech Stack:** FastAPI、SQLModel、SQLite、httpx、PyMuPDF、python-docx、python-pptx、pywin32、React Query、React 19、Vitest、Playwright。

---

## Preconditions

- [ ] Phase 1 与 Phase 2 的 exit gate 均已通过。
- [ ] 当前分支包含 `projects`、`providers`、`model_profiles` 和已验证的 OpenAI/Anthropic 适配器。
- [ ] 测试使用 `tmp_path` 或工作区 `.pytest-tmp`，不读取真实用户资料。

## Task 1: Define source-document and stable-block contracts

**Files:**
- Create: `backend/app/sources/__init__.py`
- Create: `backend/app/sources/models.py`
- Create: `backend/app/sources/schemas.py`
- Create: `backend/app/sources/repository.py`
- Create: `backend/tests/test_source_models.py`
- Modify: `backend/app/runtime/migrations.py`

- [ ] **Step 1: Write failing model and identity tests**

Create tests that assert:

```python
def test_block_identity_is_stable_for_same_document_and_locator():
    first = make_block_id("sha256-a", "page:3:block:2", "parser-v1")
    second = make_block_id("sha256-a", "page:3:block:2", "parser-v1")
    assert first == second
    assert first != make_block_id("sha256-a", "page:3:block:3", "parser-v1")


def test_source_document_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="不支持的资料格式"):
        SourceDocumentCreate(project_id="project-1", filename="archive.zip")
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_source_models.py -q
Pop-Location
```

Expected: import or contract failures because the `sources` domain does not exist.

- [ ] **Step 3: Implement the persisted contracts**

Use these exact states and discriminators:

```python
SourceKind = Literal["knowledge", "question_bank", "mixed"]
ParseStatus = Literal["queued", "parsing", "ready", "degraded", "failed"]
BlockKind = Literal["heading", "paragraph", "list", "table", "image", "question", "answer"]

class SourceDocument(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="review_project.id", index=True)
    original_name: str
    stored_name: str
    extension: str
    media_type: str
    byte_size: int
    sha256: str = Field(index=True)
    source_kind: str = "mixed"
    parse_status: str = "queued"
    parser_version: str
    page_count: int | None = None
    parse_message: str | None = None

class SourceBlock(SQLModel, table=True):
    id: str = Field(primary_key=True)
    document_id: int = Field(foreign_key="sourcedocument.id", index=True)
    ordinal: int = Field(index=True)
    locator: str
    kind: str
    text: str = ""
    page_number: int | None = None
    heading_path_json: str = "[]"
    asset_path: str | None = None
```

Implement `make_block_id` as SHA-256 of the NUL-delimited tuple `document_sha256`, `locator`, `parser_version`. The stable ID is the future vector/knowledge-base seam; never derive it from a database row number.

- [ ] **Step 4: Add migration version 3**

Create `source_document` and `source_block` tables plus indexes for project, document, ordinal, and SHA. Migration must be idempotent on a fresh Phase 1 database.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_source_models.py tests/test_migrations.py -q
Pop-Location
git add backend/app/sources backend/app/runtime/migrations.py backend/tests/test_source_models.py
git diff --cached --check
git commit -m "feat: define source documents and stable blocks"
```

## Task 2: Build format parsers and the parse cache

**Files:**
- Create: `backend/app/sources/parsers/__init__.py`
- Create: `backend/app/sources/parsers/contracts.py`
- Create: `backend/app/sources/parsers/pdf.py`
- Create: `backend/app/sources/parsers/docx.py`
- Create: `backend/app/sources/parsers/pptx.py`
- Create: `backend/app/sources/parsers/text.py`
- Create: `backend/app/sources/parsers/office.py`
- Create: `backend/app/sources/parse_cache.py`
- Create: `backend/app/sources/service.py`
- Create: `backend/tests/fixtures/sources/sample.pdf`
- Create: `backend/tests/fixtures/sources/sample.docx`
- Create: `backend/tests/fixtures/sources/sample.pptx`
- Create: `backend/tests/fixtures/sources/sample.txt`
- Create: `backend/tests/fixtures/sources/sample.md`
- Create: `backend/tests/test_source_parsers.py`
- Create: `backend/tests/test_parse_cache.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add parser contract tests before implementation**

Every parser must return the same result shape:

```python
@dataclass(frozen=True)
class ParsedSource:
    page_count: int | None
    blocks: tuple[ParsedBlock, ...]
    warnings: tuple[str, ...]
    render_paths: tuple[str, ...]

@dataclass(frozen=True)
class ParsedBlock:
    locator: str
    kind: str
    text: str
    page_number: int | None
    heading_path: tuple[str, ...]
    asset_path: str | None = None
```

Tests must cover PDF page order, DOCX headings/tables/images, PPTX slide order and speaker notes when available, TXT/Markdown decoding, and legacy `.doc`/`.ppt` Office-unavailable errors.

- [ ] **Step 2: Run parser tests and confirm RED**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_source_parsers.py tests/test_parse_cache.py -q
Pop-Location
```

- [ ] **Step 3: Add dependencies and implement modern-format parsers**

Add `python-docx` and `python-pptx` as runtime dependencies. Use PyMuPDF for PDF text extraction plus page rendering; use `python-docx` for DOCX; use `python-pptx` for PPTX; decode TXT/Markdown using UTF-8 BOM, UTF-8, then GB18030. Preserve headings and page/slide locators.

For PDF and PPTX, render a preview image per page/slide for visual-capability analysis. For DOCX, preserve inline images as assets and text structure; do not claim pixel-perfect Word pagination.

- [ ] **Step 4: Implement legacy Office conversion and explicit degradation**

`office.py` must detect Word/PowerPoint COM availability without UAC. Convert `.doc` to `.docx` and `.ppt` to `.pptx` in a per-job temporary directory, then use the modern parser. When Office is absent, return HTTP 422 with:

```json
{
  "code": "OFFICE_CONVERSION_UNAVAILABLE",
  "message": "此电脑未检测到可用的 Microsoft Office，无法解析旧版 .doc/.ppt。请另存为 .docx/.pptx 后重试。",
  "action": "convert_to_modern_format"
}
```

If visual rendering is unavailable but text extraction succeeds, mark the document `degraded`, preserve extracted text, and show the exact warning instead of failing the entire import.

- [ ] **Step 5: Implement content-addressed parse cache**

Cache key:

```python
def parse_cache_key(file_sha256: str, parser_version: str) -> str:
    raw = f"{file_sha256}\0{parser_version}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
```

Store cache manifests under `Runtime/parse-cache/<first-two>/<key>/manifest.json`. Manifest contains parser version, relative asset names, block payload, creation time, and warnings. Atomic-write to a temporary sibling and rename only after all assets exist. Never treat source rows, confirmed key points, or generated review content as cache.

- [ ] **Step 6: Verify cache hit and parser-version miss**

Tests must assert that the second identical upload performs no parser call, a parser-version change misses, incomplete manifests are discarded, and deleting parse cache does not delete formal database rows.

- [ ] **Step 7: Run and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_source_parsers.py tests/test_parse_cache.py -q
.\.venv\Scripts\python.exe -m ruff check app/sources tests/test_source_parsers.py tests/test_parse_cache.py
Pop-Location
git add backend/app/sources backend/tests/fixtures/sources backend/tests/test_source_parsers.py backend/tests/test_parse_cache.py backend/pyproject.toml
git diff --cached --check
git commit -m "feat: parse and cache review materials"
```

## Task 3: Expose source upload, preview, update, and deletion APIs

**Files:**
- Create: `backend/app/sources/router.py`
- Create: `backend/tests/test_sources_api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/tests/test_projects_api.py`

- [ ] **Step 1: Write API tests for the complete source lifecycle**

Cover:

- `POST /api/projects/{project_id}/sources` multipart upload;
- allowed extensions and maximum byte-size validation before persistence;
- `GET /api/sources/{id}` and `GET /api/sources/{id}/blocks`;
- preview asset streaming with path traversal blocked;
- `PATCH /api/sources/{id}` for `source_kind` and display name;
- `DELETE /api/sources/{id}` deleting source, blocks, preview assets, candidate key points, and dependent generated artifacts in one declared transaction;
- project deletion cascading to all of the above.

- [ ] **Step 2: Implement routes with actionable responses**

Upload response is always explicit:

```json
{
  "source_id": 12,
  "parse_status": "ready",
  "page_count": 38,
  "block_count": 214,
  "cache": "hit",
  "warnings": []
}
```

Reject encrypted/corrupt files with `FILE_ENCRYPTED` or `FILE_PARSE_FAILED`; include filename and a user action, but never include extracted document text in logs.

- [ ] **Step 3: Register the router and cascade behavior**

Register `sources.router` in `create_app`. Source and project deletion must invoke domain services rather than raw route-level SQL. Return a deletion-impact summary before destructive confirmation and the executed counts afterward.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_sources_api.py tests/test_projects_api.py -q
Pop-Location
git add backend/app/sources backend/app/projects/service.py backend/app/main.py backend/tests/test_sources_api.py backend/tests/test_projects_api.py
git diff --cached --check
git commit -m "feat: expose material ingestion APIs"
```

## Task 4: Create durable jobs, analysis runs, and worker claiming

**Files:**
- Create: `backend/app/jobs/__init__.py`
- Create: `backend/app/jobs/models.py`
- Create: `backend/app/jobs/repository.py`
- Create: `backend/app/jobs/service.py`
- Create: `backend/app/jobs/worker.py`
- Create: `backend/app/analysis/__init__.py`
- Create: `backend/app/analysis/models.py`
- Create: `backend/app/analysis/schemas.py`
- Create: `backend/app/analysis/repository.py`
- Create: `backend/tests/test_job_worker.py`
- Create: `backend/tests/test_analysis_models.py`
- Modify: `backend/app/runtime/migrations.py`
- Modify: `backend/app/runner.py`

- [ ] **Step 1: Write failing state-machine tests**

Define:

```python
JobStatus = Literal["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"]
RunStatus = Literal["queued", "running", "partial", "succeeded", "failed", "cancelled"]
BatchStatus = Literal["queued", "running", "succeeded", "failed", "skipped"]
```

Tests must prove atomic single-worker claiming, stale lease recovery, retry backoff persistence, cancellation between batches, process restart resumption, and that a succeeded batch is never called twice.

- [ ] **Step 2: Implement SQLite lease-based claiming**

Use `BEGIN IMMEDIATE`, select the oldest eligible job, update `status`, `worker_id`, `lease_expires_at`, and commit before work starts. Heartbeat renews the lease. A crashed worker leaves a recoverable lease; a new worker requeues it after expiration.

Persist `AnalysisRun` and `AnalysisBatch` with selected block IDs, prompt snapshot, provider/model snapshot, schema version, progress counts, attempts, public error code, and redacted error detail. Do not persist API keys in job payloads.

- [ ] **Step 3: Add migration version 4 and worker entry point**

`python -m app.jobs.worker` starts the loop. Keep `app.runner` as the API entry point; do not run the worker inside a FastAPI background task. Development scripts may start both processes, while Phase 4 packaging will own lifecycle supervision.

- [ ] **Step 4: Run crash/recovery tests and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_job_worker.py tests/test_analysis_models.py tests/test_migrations.py -q
Pop-Location
git add backend/app/jobs backend/app/analysis backend/app/runtime/migrations.py backend/app/runner.py backend/tests/test_job_worker.py backend/tests/test_analysis_models.py
git diff --cached --check
git commit -m "feat: add durable analysis worker"
```

## Task 5: Add exact-result caching, batching, and analysis orchestration

**Files:**
- Create: `backend/app/analysis/prompts.py`
- Create: `backend/app/analysis/cache.py`
- Create: `backend/app/analysis/service.py`
- Create: `backend/app/analysis/worker_handler.py`
- Create: `backend/tests/test_analysis_cache.py`
- Create: `backend/tests/test_analysis_worker.py`
- Modify: `backend/app/jobs/worker.py`
- Modify: `backend/app/providers/contracts.py`

- [ ] **Step 1: Write cache-key and batch-idempotency tests**

The local exact-result cache key must hash this canonical JSON:

```python
{
    "protocol": protocol,
    "provider_config_generation": provider_config_generation,
    "model": model_id,
    "content_hash": content_hash,
    "prompt_hash": prompt_hash,
    "schema_version": schema_version,
    "pipeline_version": pipeline_version,
    "parameters": normalized_parameters,
}
```

Tests must prove that identical input hits; changing prompt, model, endpoint generation, schema, selected blocks, or temperature misses; failed/partial/cancelled calls never populate cache; successful values survive process restart.

- [ ] **Step 2: Define structured candidate output**

Provider adapters must validate this internal schema regardless of wire protocol:

```python
class KeyPointCandidate(BaseModel):
    title: str
    explanation: str
    importance: Literal["core", "important", "supplementary"]
    source_block_ids: list[str] = Field(min_length=1)
    evidence_quotes: list[str]
    rationale: str

class ExtractedQuestion(BaseModel):
    question: str
    answer: str | None = None
    source_block_ids: list[str] = Field(min_length=1)
    evidence_quotes: list[str]

class AnalysisBatchResult(BaseModel):
    candidates: list[KeyPointCandidate]
    source_questions: list[ExtractedQuestion]
```

Reject model citations to blocks outside the batch. Quotes are short evidence fragments for traceability, not replacement copies of the source.

- [ ] **Step 3: Implement deterministic batching and prompt snapshots**

Sort by source/document/ordinal, keep a heading with its following blocks, cap by configured character/image budget, and store the exact block ID list per batch. Prompt order is fixed: stable system rules, project importance prompt, run override, output schema, then content. This maximizes provider-side exact-prefix cache reuse.

For Anthropic, mark the stable prefix with `cache_control`; for OpenAI-compatible endpoints, keep the exact prefix unchanged and record any provider-reported cached-token usage. Never assume a provider cache hit when usage metadata is absent.

- [ ] **Step 4: Implement cache persistence and invalidation**

Store successful results under `Runtime/ai-cache/<first-two>/<key>.json` with atomic writes and a metadata-only diagnostic index. Provider profile edits increment `config_generation`; that invalidates future keys without deleting historical files. Add a user-triggered cache-clear service that deletes only `Runtime/parse-cache` and `Runtime/ai-cache`.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_cache.py tests/test_analysis_worker.py tests/test_provider_contract.py -q
Pop-Location
git add backend/app/analysis backend/app/jobs/worker.py backend/app/providers/contracts.py backend/tests/test_analysis_cache.py backend/tests/test_analysis_worker.py
git diff --cached --check
git commit -m "feat: orchestrate cached material analysis"
```

## Task 6: Expose analysis-range, progress, candidate, and confirmation APIs

**Files:**
- Create: `backend/app/analysis/router.py`
- Create: `backend/app/keypoints/__init__.py`
- Create: `backend/app/keypoints/models.py`
- Create: `backend/app/keypoints/schemas.py`
- Create: `backend/app/keypoints/service.py`
- Create: `backend/app/keypoints/router.py`
- Create: `backend/tests/test_analysis_api.py`
- Create: `backend/tests/test_keypoints_api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runtime/migrations.py`

- [ ] **Step 1: Write the end-to-end API contract tests**

Cover:

- `POST /api/projects/{id}/analysis-runs` with `scope.mode = selected_blocks` or `all_sources`;
- empty selection, unparsed sources, missing model capability, and excessive-range validation;
- `GET /api/analysis-runs/{id}` progress and per-batch status;
- `POST /api/analysis-runs/{id}/cancel`;
- `GET /api/analysis-runs/{id}/candidates`;
- `PATCH /api/keypoint-candidates/{id}` edits before confirmation;
- bulk confirm/reject;
- CRUD and reorder for confirmed key points;
- rerun retains confirmed points and produces a distinct candidate set.

- [ ] **Step 2: Implement the route contracts and migration version 5**

`KeyPoint` persists title, explanation, importance, ordered source block IDs, short evidence fragments, origin (`manual` or `ai`), run ID, and user-edited flag. Candidate rows are disposable analysis output; confirmed rows are formal data and survive cache clearing.

Run creation returns HTTP 202:

```json
{
  "run_id": 44,
  "job_id": 81,
  "status": "queued",
  "batch_count": 7,
  "message": "已加入分析队列，可离开此页面；任务会在后台继续。"
}
```

- [ ] **Step 3: Add safe retry and correction actions**

Retry creates attempts only for failed batches. Provider/model changes require a new run snapshot. Error responses expose `action` values such as `open_provider_settings`, `select_smaller_range`, `retry_failed_batches`, and `choose_vision_model` so the UI can render a direct button.

- [ ] **Step 4: Run and commit**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_api.py tests/test_keypoints_api.py tests/test_job_worker.py -q
Pop-Location
git add backend/app/analysis/router.py backend/app/keypoints backend/app/main.py backend/app/runtime/migrations.py backend/tests/test_analysis_api.py backend/tests/test_keypoints_api.py
git diff --cached --check
git commit -m "feat: confirm AI-selected review points"
```

## Task 7: Build the material and analysis user interface

**Files:**
- Create: `frontend/src/api/sources.ts`
- Create: `frontend/src/api/analysis.ts`
- Create: `frontend/src/api/keypoints.ts`
- Create: `frontend/src/pages/project/MaterialsPage.tsx`
- Create: `frontend/src/pages/project/AnalysisPage.tsx`
- Create: `frontend/src/pages/project/KeyPointsPage.tsx`
- Create: `frontend/src/components/SourceUploader.tsx`
- Create: `frontend/src/components/SourcePreview.tsx`
- Create: `frontend/src/components/AnalysisProgress.tsx`
- Create: `frontend/src/components/KeyPointCandidateCard.tsx`
- Create: `frontend/src/pages/project/MaterialsPage.test.tsx`
- Create: `frontend/src/pages/project/AnalysisPage.test.tsx`
- Create: `frontend/src/pages/project/KeyPointsPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing interaction tests**

Test upload drag/drop plus file picker, format/size hints, parse progress and degraded warnings, page/block range selection, `all_sources` warning, project prompt plus per-run override, model capability blocking, progress polling, cancellation, retry, candidate edit/confirm/reject, and empty/error states.

- [ ] **Step 2: Implement React Query resources**

Use separate query keys:

```ts
export const sourceKeys = {
  list: (projectId: string) => ["projects", projectId, "sources"] as const,
  blocks: (sourceId: number) => ["sources", sourceId, "blocks"] as const,
};

export const analysisKeys = {
  run: (runId: number) => ["analysis-runs", runId] as const,
  candidates: (runId: number) => ["analysis-runs", runId, "candidates"] as const,
};
```

Poll only while `queued`, `running`, or `retry_wait`; stop after terminal status. Invalidate source, run, candidate, and key-point queries at the exact mutation boundary rather than globally.

- [ ] **Step 3: Implement obvious guidance and correction UI**

Materials page explains supported formats before upload. Analysis page displays estimated pages/blocks and says that AI results require confirmation. Whole-document analysis requires an explicit confirmation when the range exceeds the configured warning threshold. Errors render a headline, cause, affected source/batch, and the API-provided action button.

The candidate screen groups by core/important/supplementary, shows source links, allows inline edits, bulk selection, confirm/reject, and never auto-confirms on completion.

- [ ] **Step 4: Run and commit**

Run:

```powershell
Push-Location frontend
npm test -- MaterialsPage.test.tsx AnalysisPage.test.tsx KeyPointsPage.test.tsx
npm run lint
npm run build
Pop-Location
git add frontend/src/api frontend/src/pages/project frontend/src/components/SourceUploader.tsx frontend/src/components/SourcePreview.tsx frontend/src/components/AnalysisProgress.tsx frontend/src/components/KeyPointCandidateCard.tsx frontend/src/App.tsx frontend/src/styles.css
git diff --cached --check
git commit -m "feat: add material analysis workspace"
```

## Task 8: Prove the Phase 3 full story

**Files:**
- Create: `backend/tests/test_ingestion_analysis_story.py`
- Create: `frontend/e2e/material-analysis.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Add backend full-story fixtures and test**

Using fake provider responses, prove both paths:

1. Create project → upload PDF/DOCX/PPTX/TXT/Markdown → choose blocks → analyze → edit candidates → confirm.
2. Create project → upload material → scan all sources → simulate worker crash after one batch → resume → retry one provider error → confirm.

Assert parse and AI cache hits on exact reruns, misses after prompt/model change, stable source block IDs, and no duplicate confirmed points.

- [ ] **Step 2: Add Playwright flow**

The browser test uses deterministic backend fixtures and verifies visible operation hints, actionable provider/format errors, progress restoration after reload, source jumping, and confirmation requirement.

- [ ] **Step 3: Update README for implemented Phase 3 behavior**

Document supported formats, Office conversion requirements, degradation rules, worker startup, data/cache locations, cache clearing semantics, and the difference between candidate and confirmed content.

- [ ] **Step 4: Run the Phase 3 exit gate**

Run:

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase3-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $base tests/test_source_models.py tests/test_source_parsers.py tests/test_parse_cache.py tests/test_sources_api.py tests/test_job_worker.py tests/test_analysis_cache.py tests/test_analysis_worker.py tests/test_analysis_api.py tests/test_keypoints_api.py tests/test_ingestion_analysis_story.py
.\.venv\Scripts\python.exe -m ruff check app tests
Pop-Location
Push-Location frontend
npm test
npm run lint
npm run build
npm run test:e2e -- material-analysis.spec.ts
Pop-Location
rg -n -i "semantic cache|vector database|自动确认" backend frontend README.md
```

Expected: tests/build pass; the final search returns only documentation statements that semantic cache/vector database/automatic confirmation are intentionally absent, not active implementations.

- [ ] **Step 5: Commit the phase gate**

Run:

```powershell
git add backend/tests/test_ingestion_analysis_story.py frontend/e2e/material-analysis.spec.ts README.md
git diff --cached --check
git commit -m "test: verify material analysis workflow"
```

## Phase 3 exit criteria

- [ ] All approved file formats import under their complete or explicit-degradation rules.
- [ ] Stable content block IDs remain unchanged for identical file, locator, and parser version.
- [ ] Selected-range and whole-document analysis both run through the durable worker.
- [ ] Worker restart, cancellation, retry, and partial failure never duplicate succeeded batches.
- [ ] Parse cache, provider-side prompt cache signaling, and local exact-result cache have observable hit/miss behavior.
- [ ] AI output remains editable candidate data until the user explicitly confirms it.
- [ ] No semantic cache, vector database, automatic confirmation, or secret/content logging has been introduced.
