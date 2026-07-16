# 拾要 Phase 1 Foundation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans only when the user explicitly asks to execute this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除旧数据和 Codex 接入，建立“拾要”的品牌、运行标识、新数据库与复习项目领域骨架。

**Architecture:** 保留桌面启动、FastAPI、SQLite、统一错误和 React shell；替换旧 Course/Lesson 领域入口。Phase 1 只交付空白复习项目管理，不实现资料分析和复习生成。

**Tech Stack:** FastAPI、SQLModel、SQLite、React、TypeScript、React Query、pytest、Vitest。

---

### Task 1: Add a guard test, remove Codex, and reset approved workspace data

**Files:**
- Create: `backend/tests/test_product_surface.py`
- Delete: `backend/app/ai/codex.py`
- Delete: `backend/tests/test_codex_provider.py`
- Modify: `backend/pyproject.toml:1-43`
- Modify: `backend/app/ai/settings.py:1-113`
- Modify: `setup.ps1:1-40`
- Modify: `scripts/build-windows.ps1:1-100`
- Modify: `packaging/semiconductor-review.spec:1-68`

- [ ] **Step 1: Write the failing product-surface test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_source_has_no_codex_integration():
    checked = [
        ROOT / "backend" / "app",
        ROOT / "backend" / "pyproject.toml",
        ROOT / "setup.ps1",
        ROOT / "scripts" / "build-windows.ps1",
        ROOT / "packaging",
    ]
    offenders: list[str] = []
    for path in checked:
        files = path.rglob("*") if path.is_dir() else [path]
        for file in files:
            if file.is_file() and file.suffix.lower() in {".py", ".toml", ".ps1", ".spec"}:
                if "codex" in file.read_text(encoding="utf-8-sig").lower():
                    offenders.append(str(file.relative_to(ROOT)))
    assert offenders == []
```

- [ ] **Step 2: Run the guard and verify it fails**

Run:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_product_surface.py -q
Pop-Location
```

Expected: FAIL and list `backend/app/ai/codex.py`, build scripts, spec, and settings.

- [ ] **Step 3: Remove Codex implementation and dependency**

Delete the two Codex files. In `backend/pyproject.toml`, remove the `codex` optional dependency. In `AISettingsInput`, temporarily restrict the provider to OpenAI until Phase 2 replaces the entire settings service:

```python
class AISettingsInput(BaseModel):
    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    vision_enabled: bool = True
    api_key: str | None = Field(default=None, exclude=True)
    clear_api_key: bool = False
```

`default_provider_factory()` must always return `OpenAICompatibleProvider`; remove all Codex branches. Remove Codex installation/download/runtime collection from `setup.ps1`, `scripts/build-windows.ps1`, and the PyInstaller spec.

- [ ] **Step 4: Safely clear only the approved workspace directories**

Run from the implementation worktree after stopping the source service:

```powershell
.\stop.ps1
$root = (Resolve-Path '.').Path
$targets = @('data', 'Backups', 'Logs', 'Runtime') | ForEach-Object {
    $path = [IO.Path]::GetFullPath((Join-Path $root $_))
    if (-not $path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside worktree: $path"
    }
    $path
}
$targets | ForEach-Object {
    if (Test-Path -LiteralPath $_) {
        Get-ChildItem -LiteralPath $_ -Force | Remove-Item -Recurse -Force
    }
    New-Item -ItemType Directory -Path $_ -Force | Out-Null
}
```

Expected: only the four worktree directories are empty. Do not inspect or modify `%LOCALAPPDATA%\SemiconductorReview` and do not touch `%SystemDrive%/`.

- [ ] **Step 5: Run the guard again**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/tests/test_product_surface.py backend/pyproject.toml backend/app/ai/settings.py setup.ps1 scripts/build-windows.ps1 packaging/semiconductor-review.spec
git add -u backend/app/ai/codex.py backend/tests/test_codex_provider.py
git commit -m "refactor: remove codex integration"
```

### Task 2: Establish Shiyao identity, paths, and a fresh database

**Files:**
- Modify: `backend/app/runtime/paths.py:10-49`
- Modify: `backend/app/runtime/migrations.py:8-49`
- Modify: `backend/app/shared/database.py:6-16`
- Modify: `backend/app/main.py:32-166`
- Modify: `backend/tests/test_runtime_paths.py:1-47`
- Modify: `backend/tests/test_migrations.py:1-54`
- Modify: `backend/tests/test_local_hosting.py:1-71`

- [ ] **Step 1: Write failing identity and fresh-schema tests**

```python
def test_frozen_app_uses_shiyao_user_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.discover(frozen=True, resource_root=tmp_path / "resources")
    assert paths.root == tmp_path / "Shiyao"
    assert paths.data == tmp_path / "Shiyao" / "Data"


def test_new_database_has_shiyao_product_version(tmp_path):
    database = tmp_path / "shiyao.db"
    migrate_database(database, tmp_path / "Backups")
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
```

Update the readiness assertion to expect `application == "shiyao-review"` and `protocol_version == 2`.

- [ ] **Step 2: Run focused tests and verify failure**

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase1-paths-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_paths.py tests/test_migrations.py tests/test_local_hosting.py --basetemp $base
Pop-Location
```

Expected: FAIL on `SemiconductorReview`, `review.db`, and old readiness marker.

- [ ] **Step 3: Implement the new identity**

Use constants rather than scattered literals:

```python
APP_ID = "shiyao-review"
APP_PROTOCOL_VERSION = 2
APP_DATA_DIR_NAME = "Shiyao"
DATABASE_NAME = "shiyao.db"
```

`AppPaths.discover()` must read `SHIYAO_ROOT`, `SHIYAO_DATA_DIR`, and `SHIYAO_FRONTEND_DIST`. `create_database()` and `create_default_app()` must use `shiyao.db`. `FastAPI(title="Shiyao Review")` and `/ready` must expose the new application marker.

Because old data is intentionally deleted, `migrate_database()` only supports the new schema line; it must reject a database whose tables exist with product marker other than `shiyao-review` rather than attempting legacy conversion.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/runtime/paths.py backend/app/runtime/migrations.py backend/app/shared/database.py backend/app/main.py backend/tests/test_runtime_paths.py backend/tests/test_migrations.py backend/tests/test_local_hosting.py
git commit -m "refactor: establish shiyao runtime identity"
```

### Task 3: Add review-project domain models and CRUD API

**Files:**
- Create: `backend/app/projects/__init__.py`
- Create: `backend/app/projects/models.py`
- Create: `backend/app/projects/router.py`
- Create: `backend/tests/test_projects_api.py`
- Modify: `backend/app/main.py:1-166`
- Delete: `backend/app/courses/`
- Delete: `backend/app/content/`
- Delete: `backend/app/learning/`
- Delete: `backend/app/review/`
- Delete: `backend/tests/test_courses_api.py`
- Delete: `backend/tests/test_content_ingestion.py`
- Delete: `backend/tests/test_learning_ai_adapter.py`
- Delete: `backend/tests/test_learning_review.py`
- Delete: `backend/tests/test_provider_contract.py`
- Delete: `backend/tests/test_schedule.py`

- [ ] **Step 1: Write the failing project lifecycle test**

```python
def test_review_project_lifecycle(tmp_path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            json={"name": "期末总复习", "description": "材料综合复习", "importance_prompt": "优先公式与易错点"},
        )
        assert created.status_code == 201
        project = created.json()
        assert project["name"] == "期末总复习"
        assert client.get("/api/projects").json() == [project]
        assert client.get(f"/api/projects/{project['id']}").json() == project
        assert client.delete(f"/api/projects/{project['id']}").status_code == 204
```

- [ ] **Step 2: Run the test and verify 404**

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase1-projects-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_projects_api.py --basetemp $base
Pop-Location
```

Expected: FAIL because `/api/projects` is not registered.

- [ ] **Step 3: Implement focused models**

```python
class ReviewProject(SQLModel, table=True):
    __tablename__ = "review_project"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    importance_prompt: str = Field(default="", max_length=10000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReviewProjectCreate(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    importance_prompt: str = Field(default="", max_length=10000)
```

Implement POST/GET/list/PATCH/DELETE routes under `/api/projects`. Keep HTTP parsing in the router and project deletion orchestration in a private service function so later phases can add source cascades without growing the route.

- [ ] **Step 4: Register the router and remove course routes**

Replace `courses_router` with `projects_router` in `backend/app/main.py`. Remove the old content, learning, review, and course routers together because they form one mutually dependent legacy domain; leaving half of that graph would make application imports invalid. Keep backup, desktop, runtime, system, shared, and the temporary OpenAI provider.

- [ ] **Step 5: Run focused and shared error tests**

Replace the old router-registration assertion in `test_app_integration.py` with an explicit Phase 1 smoke contract:

```python
def test_app_registers_project_routes_and_no_legacy_domain_routes(tmp_path):
    app = create_app(tmp_path / "data", secret_store=MemorySecretStore())
    paths = {route.path for route in app.routes}
    assert "/api/projects" in paths
    assert "/api/courses" not in paths
    assert "/api/lessons/{lesson_id}" not in paths
    assert "/api/review/due" not in paths
```

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase1-projects-pass-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_projects_api.py tests/test_app_integration.py --basetemp $base
Pop-Location
```

Expected: project tests PASS; old app integration assertions fail only where they still expect courses, and those assertions must be replaced with project registration assertions before commit.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/projects backend/app/main.py backend/tests/test_projects_api.py backend/tests/test_app_integration.py
git add -u backend/app/courses backend/app/content backend/app/learning backend/app/review backend/tests/test_courses_api.py backend/tests/test_content_ingestion.py backend/tests/test_learning_ai_adapter.py backend/tests/test_learning_review.py backend/tests/test_provider_contract.py backend/tests/test_schedule.py
git commit -m "feat: add review project domain"
```

### Task 4: Rebrand the frontend shell and add project workspace pages

**Files:**
- Create: `frontend/src/pages/ProjectsPage.tsx`
- Create: `frontend/src/pages/ProjectDetailPage.tsx`
- Create: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/pages/MasteryPage.tsx`
- Create: `frontend/src/pages/ProjectsPage.test.tsx`
- Modify: `frontend/src/App.tsx:1-85`
- Modify: `frontend/src/api/client.ts:1-326`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Delete: `frontend/src/pages/CoursesPage.tsx`
- Delete: `frontend/src/pages/CourseDetailPage.tsx`
- Delete: `frontend/src/pages/LessonPage.tsx`
- Delete and replace: `frontend/src/pages/ProgressPage.tsx`
- Delete and replace: `frontend/src/pages/ReviewPage.tsx`

- [ ] **Step 1: Write failing navigation and project tests**

```tsx
it('creates a review project and opens its five-tab workspace', async () => {
  render(<AppRoutes />)
  await user.click(await screen.findByRole('link', { name: '项目' }))
  await user.click(screen.getByRole('button', { name: '新建复习项目' }))
  await user.type(screen.getByLabelText('项目名称'), '期末总复习')
  await user.click(screen.getByRole('button', { name: '创建项目' }))
  expect(await screen.findByRole('heading', { name: '期末总复习' })).toBeInTheDocument()
  for (const tab of ['概览', '资料', '重点', '复习', '掌握情况']) {
    expect(screen.getByRole('tab', { name: tab })).toBeInTheDocument()
  }
})
```

- [ ] **Step 2: Run the tests and verify failure**

```powershell
Push-Location frontend
npm test -- --run src/pages/ProjectsPage.test.tsx src/App.test.tsx
Pop-Location
```

Expected: FAIL because new routes and labels do not exist.

- [ ] **Step 3: Replace frontend types and routes**

```ts
export type ReviewProject = {
  id: string
  name: string
  description: string
  importance_prompt: string
  created_at: string
  updated_at: string
}
```

Replace the old course/lesson/review API types with system, backup, and project APIs only. Add `listProjects`, `createProject`, `getProject`, `updateProject`, and `deleteProject`. Routes become `/projects`, `/projects/:id`, `/review`, `/mastery`, `/settings`, and `/setup`. Brand text becomes `拾要` and `从资料中拾取真正重要的内容`.

`DashboardPage` summarizes projects only. `ProjectDetailPage` renders the five tabs with explicit empty states; new `ReviewPage` and `MasteryPage` also render honest Phase 1 empty states. Later phases replace those empty states with working features.

- [ ] **Step 4: Run frontend tests and build**

```powershell
Push-Location frontend
npm test
npm run build
Pop-Location
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/api/client.ts frontend/src/styles.css frontend/src/App.test.tsx frontend/src/pages/DashboardPage.tsx frontend/src/pages/ProjectsPage.tsx frontend/src/pages/ProjectDetailPage.tsx frontend/src/pages/ProjectsPage.test.tsx frontend/src/pages/ReviewPage.tsx frontend/src/pages/MasteryPage.tsx
git add -u frontend/src/pages/CoursesPage.tsx frontend/src/pages/CourseDetailPage.tsx frontend/src/pages/LessonPage.tsx frontend/src/pages/ProgressPage.tsx
git commit -m "feat: add shiyao project workspace"
```

### Task 5: Complete the Phase 1 gate

**Files:**
- Modify: `README.md`
- Modify: `backend/tests/test_full_story.py`
- Modify: `frontend/e2e/app.spec.ts`

- [ ] **Step 1: Replace the obsolete full-story test with a Phase 1 smoke story**

The test creates an app, creates one review project, lists it, verifies `/ready`, and deletes it. It must not import `Course`, `Lesson`, or schedule helpers.

- [ ] **Step 2: Replace the E2E smoke path**

```ts
test('creates and opens an empty review project', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: '项目' }).click()
  await page.getByRole('button', { name: '新建复习项目' }).click()
  await page.getByLabel('项目名称').fill('资格考试总复习')
  await page.getByRole('button', { name: '创建项目' }).click()
  await expect(page.getByRole('heading', { name: '资格考试总复习' })).toBeVisible()
})
```

- [ ] **Step 3: Update README for the Phase 1 boundary**

Document that provider setup, imports, analysis, and study workflows arrive in subsequent phases; do not claim incomplete features work.

- [ ] **Step 4: Run the phase gate**

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase1-gate-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $base
.\.venv\Scripts\python.exe -m ruff check app tests
Pop-Location
Push-Location frontend
npm test
npm run build
npm run lint
Pop-Location
rg -n -i "codex|openai-codex|codex_cli_bin" backend frontend setup.ps1 scripts packaging README.md
rg -n -i "半导体|课后复习|SemiconductorReview" backend/app frontend/src README.md
```

Expected: tests/build/lint PASS. The Codex scan has no matches anywhere in runtime, setup, build, or packaging inputs. The old-brand scan has no matches in the API/application UI or README; installer and executable filenames are intentionally renamed together in Phase 4 so they never enter a half-renamed release.

- [ ] **Step 5: Commit**

```powershell
git add README.md backend/tests/test_full_story.py frontend/e2e/app.spec.ts
git commit -m "test: establish shiyao foundation gate"
```
