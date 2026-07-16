# 拾要 Phase 2 AI Providers Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans only when the user explicitly asks to execute this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可保存多套 OpenAI 兼容或 Anthropic 服务、获取/手输模型、分层校验能力并安全启用的第三方 AI 配置系统。

**Architecture:** 用 `providers` 领域替换临时单配置 `ai` 模块。协议适配器共享统一契约和错误分类，配置存 SQLite，密钥按 profile ID 存 Windows 凭据库；前端用服务卡片和六步配置流程驱动。

**Tech Stack:** FastAPI、SQLModel、httpx、keyring、Pydantic、React Query、Vitest。

---

### Task 1: Define provider profiles, model profiles, and credential namespaces

**Files:**
- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/models.py`
- Create: `backend/app/providers/schemas.py`
- Create: `backend/app/providers/credentials.py`
- Create: `backend/tests/test_provider_profiles.py`
- Delete: `backend/app/ai/`
- Delete: `backend/tests/test_ai_settings_api.py`

- [ ] **Step 1: Write failing profile and secret tests**

```python
def test_profiles_keep_only_secret_reference_in_database(tmp_path):
    secrets = MemorySecretStore()
    service = ProviderProfileService(create_database(tmp_path), secrets)
    profile = service.create(
        ProviderProfileCreate(
            name="主力服务",
            protocol="openai_compatible",
            base_url="https://example.test/v1",
            api_key="sk-secret-value",
        )
    )
    assert profile.api_key_configured is True
    assert secrets.get(f"provider:{profile.id}:api_key") == "sk-secret-value"
    assert "sk-secret-value" not in (tmp_path / "shiyao.db").read_bytes().decode("latin1")
```

- [ ] **Step 2: Run and verify failure**

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase2-profiles-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_provider_profiles.py --basetemp $base
Pop-Location
```

Expected: FAIL because `app.providers` does not exist.

- [ ] **Step 3: Implement profile models**

```python
class AIProviderProfile(SQLModel, table=True):
    __tablename__ = "ai_provider_profile"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(min_length=1, max_length=100)
    protocol: str = Field(index=True)
    base_url: str
    enabled: bool = False
    is_default: bool = False
    credential_generation: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ModelProfile(SQLModel, table=True):
    __tablename__ = "model_profile"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    provider_id: str = Field(foreign_key="ai_provider_profile.id", index=True)
    model_id: str
    display_name: str
    text_status: str = "untested"
    structured_status: str = "untested"
    vision_status: str = "untested"
    validated_at: datetime | None = None
```

Pydantic create/update/read schemas accept `api_key` only on writes with `exclude=True`. Allow only `openai_compatible` and `anthropic` protocol literals.

- [ ] **Step 4: Implement per-profile credential storage**

```python
def credential_key(profile_id: str) -> str:
    return f"provider:{profile_id}:api_key"


def replace_api_key(store: SecretStore, profile: AIProviderProfile, value: str) -> None:
    store.set(credential_key(profile.id), value)
    profile.credential_generation += 1
```

Delete the credential when a profile is deleted. Increment `credential_generation` on key replacement so capability and result caches can invalidate without hashing or persisting the secret.

- [ ] **Step 5: Replace old imports and run tests**

Delete `backend/app/ai` only after `main.py` temporarily stops constructing `AISettingsService`; setup completion may remain false until a provider is enabled.

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/providers backend/app/main.py backend/tests/test_provider_profiles.py
git add -u backend/app/ai backend/tests/test_ai_settings_api.py
git commit -m "feat: add ai provider profiles"
```

### Task 2: Normalize endpoints and classify provider errors

**Files:**
- Create: `backend/app/providers/endpoints.py`
- Create: `backend/app/providers/errors.py`
- Create: `backend/tests/test_provider_endpoints.py`
- Create: `backend/tests/test_provider_errors.py`

- [ ] **Step 1: Write endpoint table tests**

```python
@pytest.mark.parametrize(
    ("protocol", "entered", "models", "inference"),
    [
        ("openai_compatible", "https://host.test", "https://host.test/v1/models", "https://host.test/v1/chat/completions"),
        ("openai_compatible", "https://host.test/v1/", "https://host.test/v1/models", "https://host.test/v1/chat/completions"),
        ("anthropic", "https://host.test", "https://host.test/v1/models", "https://host.test/v1/messages"),
        ("anthropic", "https://host.test/v1", "https://host.test/v1/models", "https://host.test/v1/messages"),
    ],
)
def test_resolved_endpoints(protocol, entered, models, inference):
    resolved = resolve_endpoints(protocol, entered)
    assert resolved.models_url == models
    assert resolved.inference_url == inference
```

- [ ] **Step 2: Write error-mapping tests**

```python
@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "upstream_auth_failed"), (403, "upstream_forbidden"), (404, "upstream_endpoint_not_found"), (405, "upstream_method_not_allowed"), (429, "upstream_rate_limited")],
)
def test_http_status_has_actionable_code(status, code):
    assert map_http_error(httpx.Response(status, request=httpx.Request("GET", "https://x"))).code == code
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_provider_endpoints.py tests/test_provider_errors.py -q
Pop-Location
```

Expected: FAIL because resolver and mapping do not exist.

- [ ] **Step 4: Implement strict URL validation and typed errors**

Reject non-HTTP(S) schemes, credentials embedded in URLs, query strings, fragments, and empty hosts. Return `ResolvedEndpoints(base_url, models_url, inference_url)` for UI preview.

Define `ProviderError(AppError)` subclasses for auth, forbidden, endpoint mismatch, rate limit, timeout, TLS/network, invalid response, model unavailable, and prompt cache unsupported. Messages must include one safe next action and never include response bodies verbatim.

- [ ] **Step 5: Run tests and commit**

Run the Step 3 command; expect PASS.

```powershell
git add backend/app/providers/endpoints.py backend/app/providers/errors.py backend/tests/test_provider_endpoints.py backend/tests/test_provider_errors.py
git commit -m "feat: normalize provider endpoints and errors"
```

### Task 3: Implement OpenAI-compatible and Anthropic adapters

**Files:**
- Create: `backend/app/providers/contracts.py`
- Create: `backend/app/providers/openai_compatible.py`
- Create: `backend/app/providers/anthropic.py`
- Create: `backend/tests/test_provider_contract.py`
- Create: `backend/tests/test_openai_provider.py`
- Create: `backend/tests/test_anthropic_provider.py`

- [ ] **Step 1: Write contract tests with MockTransport**

```python
@pytest.mark.asyncio
async def test_openai_lists_models_with_bearer_key():
    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"id": "vision-model", "owned_by": "test"}]})
    adapter = OpenAICompatibleAdapter(endpoints=resolved, api_key="sk-test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert [model.id for model in await adapter.list_models()] == ["vision-model"]


@pytest.mark.asyncio
async def test_anthropic_lists_models_with_native_headers():
    async def handler(request: httpx.Request):
        assert request.headers["x-api-key"] == "sk-ant-test"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"data": [{"id": "claude-test", "display_name": "Claude Test"}], "has_more": False})
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_provider_contract.py tests/test_openai_provider.py tests/test_anthropic_provider.py -q
Pop-Location
```

Expected: FAIL because adapters do not exist.

- [ ] **Step 3: Define the provider contract**

```python
class ProviderAdapter(Protocol):
    async def list_models(self) -> list[RemoteModel]: ...
    async def generate_json(self, request: StructuredRequest[T]) -> ProviderResult[T]: ...
    async def generate_text(self, request: TextRequest) -> ProviderResult[str]: ...
```

`ProviderResult` includes parsed value, input/output tokens, cached input tokens if reported, provider request ID, and safe model ID.

`test_provider_contract.py` supplies one deterministic fake adapter and asserts that both production adapters conform to the same text, structured, image-content, usage, cancellation, and redacted-error contract. This is a new Phase 2 contract test, not the deleted legacy learning-provider test.

- [ ] **Step 4: Implement both adapters**

OpenAI sends JSON schema through `response_format`. Anthropic sends schema instructions and validates the returned JSON locally; one repair request is allowed for either protocol. Images are base64 content blocks. Both adapters use the common error mapper and a 60-second request timeout.

- [ ] **Step 5: Run tests and commit**

Run the Step 2 command; expect PASS.

```powershell
git add backend/app/providers/contracts.py backend/app/providers/openai_compatible.py backend/app/providers/anthropic.py backend/tests/test_provider_contract.py backend/tests/test_openai_provider.py backend/tests/test_anthropic_provider.py
git commit -m "feat: add openai and anthropic adapters"
```

### Task 4: Add model discovery, manual fallback, capability probes, and prompt-cache reporting

**Files:**
- Create: `backend/app/providers/service.py`
- Create: `backend/app/providers/probes.py`
- Create: `backend/app/providers/router.py`
- Create: `backend/tests/test_provider_api.py`
- Create: `backend/tests/test_provider_probes.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write API behavior tests**

```python
def test_unsupported_model_list_allows_manual_model(tmp_path):
    client = configured_client(tmp_path, models_status=404)
    fetched = client.post("/api/providers/p1/models:refresh")
    assert fetched.status_code == 422
    assert fetched.json()["title"] == "upstream_endpoint_not_found"
    manual = client.post("/api/providers/p1/models", json={"model_id": "relay-model", "display_name": "relay-model"})
    assert manual.status_code == 201


def test_provider_cannot_enable_until_required_probes_pass(tmp_path):
    client = configured_client(tmp_path)
    response = client.post("/api/providers/p1:enable")
    assert response.status_code == 409
    assert response.json()["title"] == "provider_not_validated"
```

- [ ] **Step 2: Run and verify failure**

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase2-api-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_provider_api.py tests/test_provider_probes.py --basetemp $base
Pop-Location
```

Expected: FAIL because provider router/service/probes do not exist.

- [ ] **Step 3: Implement discovery cache and probe fixtures**

Store `models_fetched_at`; return cached model candidates for 15 minutes unless `force=true`. Probe text with a short deterministic request, structured output with `{"ok": true, "message": "..."}`, and vision with a bundled small image whose expected content is fixed.

Persist each probe as `passed`, `failed`, or `unsupported`, plus safe error code and validation timestamp. Changing base URL, credential generation, or model ID resets all probe states.

- [ ] **Step 4: Implement Anthropic prompt-cache probe**

For Anthropic, send top-level `cache_control={"type":"ephemeral"}`. If a proxy rejects only that field, set `prompt_cache_status="unsupported"` and allow normal inference when the user disables prompt caching. Record `cache_read_input_tokens` and `cache_creation_input_tokens` when returned.

- [ ] **Step 5: Implement routes and registration**

Provide CRUD `/api/providers`, endpoint preview, `models:refresh`, manual model creation, `models/{id}:probe`, enable/disable, and default-selection endpoints. Register the router in `main.py`.

- [ ] **Step 6: Run tests and commit**

Run the Step 2 command; expect PASS.

```powershell
git add backend/app/providers/service.py backend/app/providers/probes.py backend/app/providers/router.py backend/app/main.py backend/tests/test_provider_api.py backend/tests/test_provider_probes.py
git commit -m "feat: add model discovery and capability probes"
```

### Task 5: Build the provider-card setup and settings experience

**Files:**
- Create: `frontend/src/components/providers/ProviderCard.tsx`
- Create: `frontend/src/components/providers/ProviderEditor.tsx`
- Create: `frontend/src/components/providers/ModelManager.tsx`
- Create: `frontend/src/components/providers/CapabilityBadges.tsx`
- Create: `frontend/src/components/providers/ProviderError.tsx`
- Create: `frontend/src/components/providers/ProviderEditor.test.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/SetupPage.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write the failing six-step setup test**

```tsx
it('previews endpoints, fetches models, probes capabilities, and enables a provider', async () => {
  render(<SetupPage />)
  await user.selectOptions(screen.getByLabelText('协议'), 'anthropic')
  await user.type(screen.getByLabelText('API 地址'), 'https://relay.test')
  expect(screen.getByText('https://relay.test/v1/models')).toBeVisible()
  await user.type(screen.getByLabelText('API Key'), 'sk-test')
  await user.click(screen.getByRole('button', { name: '获取模型' }))
  await user.selectOptions(await screen.findByLabelText('模型'), 'claude-test')
  await user.click(screen.getByRole('button', { name: '校验模型能力' }))
  expect(await screen.findByText('视觉：通过')).toBeVisible()
  await user.click(screen.getByRole('button', { name: '启用此服务' }))
})
```

- [ ] **Step 2: Run and verify failure**

```powershell
Push-Location frontend
npm test -- --run src/components/providers/ProviderEditor.test.tsx
Pop-Location
```

Expected: FAIL because provider components do not exist.

- [ ] **Step 3: Implement typed API methods and components**

The editor has exactly six visible stages: protocol, address/key, model discovery, model selection, probes, enable. Show resolved endpoint URLs under the address field. Keep key masked and clear the form value after save. `ProviderError` maps safe error codes to one primary action and an expandable technical-detail block.

- [ ] **Step 4: Replace setup and settings pages**

`SetupPage` completes only when one provider/model is enabled and default. `SettingsPage` lists multiple cards, allows temporary disable, revalidation, refresh, default selection, and deletion confirmation. Keep backup/system sections intact.

- [ ] **Step 5: Run frontend tests and build**

```powershell
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/providers frontend/src/pages/SettingsPage.tsx frontend/src/pages/SetupPage.tsx frontend/src/api/client.ts frontend/src/styles.css
git commit -m "feat: add guided provider configuration"
```

### Task 6: Complete the Phase 2 gate

**Files:**
- Modify: `backend/tests/test_full_story.py`
- Modify: `frontend/e2e/app.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Add a provider setup integration story**

Use `httpx.MockTransport` to create an Anthropic profile, fetch one model, pass three probes, enable it, and verify setup completion. Add the equivalent OpenAI contract case.

- [ ] **Step 2: Add first-run E2E with mocked provider endpoints**

The Playwright test must assert field-level URL errors, manual model fallback after a mocked 404, and that a model cannot enable before probes pass.

- [ ] **Step 3: Update README**

Document OpenAI-compatible and Anthropic setup, model retrieval fallback, capability badges, credential storage, and that no user material is sent during probes.

- [ ] **Step 4: Run the phase gate**

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('phase2-gate-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $base
.\.venv\Scripts\python.exe -m ruff check app tests
Pop-Location
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location
```

Expected: PASS with no live provider calls.

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/test_full_story.py frontend/e2e/app.spec.ts README.md
git commit -m "test: verify provider setup flow"
```
