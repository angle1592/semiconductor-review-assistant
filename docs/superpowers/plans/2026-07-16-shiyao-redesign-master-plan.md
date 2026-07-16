# 拾要重构 Master Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans only when the user explicitly asks to execute this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已批准规格把“半导体课后复习台”重构为通用资料总复习工具“拾要”，删除旧数据和 Codex 接入，并交付可安装、可恢复、可验证的 Windows 应用。

**Architecture:** 继续使用 React/FastAPI/SQLite 的本地单体架构，按复习项目、资料、分析、重点、题目、学习和提供商重建领域边界。长任务由本地 worker 读取 SQLite 队列执行；模型端提示缓存与本地精确缓存分层实现，不引入 Redis 或云端服务。

**Tech Stack:** Python 3.11、FastAPI、SQLModel、SQLite、httpx、PyMuPDF、python-docx、pywin32、React 19、TypeScript、React Query、Vitest、Playwright、PyInstaller、Inno Setup。

---

## Source of truth

- 设计规格：`docs/superpowers/specs/2026-07-16-shiyao-general-review-redesign.md`
- 计划分支：`codex/shiyao-redesign-plan`
- 计划 worktree：`C:\Users\Tanfu\Desktop\t\.worktrees\shiyao-redesign-plan`

任何实现细节与规格冲突时，以规格为准；先修订规格并由用户确认，再更新计划。

## Execution order

| Phase | Plan | Working result | Exit gate |
|---|---|---|---|
| 1 | `2026-07-16-shiyao-phase-1-foundation-plan.md` | 新品牌、新数据目录、新领域骨架、项目 CRUD，Codex 完全删除 | 后端与前端基础测试通过，源码扫描无 Codex 接入 |
| 2 | `2026-07-16-shiyao-phase-2-providers-plan.md` | 多 AI 服务、模型获取、能力校验、Anthropic/OpenAI 适配 | 两种协议契约测试和首次配置 E2E 通过 |
| 3 | `2026-07-16-shiyao-phase-3-ingestion-analysis-plan.md` | 多格式导入、内容块、任务 worker、缓存、重点确认 | 人工选页和全文扫描完整集成测试通过 |
| 4 | `2026-07-16-shiyao-phase-4-study-release-plan.md` | 原题、复习成果、掌握度、备份、打包与全流程验收 | 全量测试、冻结应用和安装包烟雾测试通过 |

各阶段必须按顺序执行。阶段提交保留在同一实现分支；每个阶段通过 exit gate 后才能进入下一阶段。

## Global execution rules

- [ ] **Step 1: Use a clean implementation worktree**

Run:

```powershell
git worktree add .worktrees\shiyao-redesign -b codex/shiyao-redesign codex/shiyao-redesign-plan
```

Expected: 新 worktree 指向包含规格和计划的提交，主目录中的 `%SystemDrive%/` 不会进入实现分支。

- [ ] **Step 2: Record the baseline without requesting elevation**

Run:

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('plan-baseline-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $base -k "not windows_launcher"
Pop-Location
Push-Location frontend
npm test
npm run build
Pop-Location
```

Expected: 记录通过数和任何既有失败；pytest 临时目录位于工作区，不访问受限的用户 Temp。

- [ ] **Step 3: Keep destructive reset inside Phase 1 only**

只有 Phase 1 的明确步骤可以清空工作区 `data/`、`Backups/`、`Logs/`、`Runtime/` 内容。不得触碰 `%LOCALAPPDATA%\SemiconductorReview`，不得删除 `%SystemDrive%/`。

- [ ] **Step 4: Commit at every task boundary**

每个任务只暂存其 `Files` 列表中的路径，运行 `git diff --cached --check` 后提交。不得使用 `git add .`。

- [ ] **Step 5: Run the complete release gate after Phase 4**

Run:

```powershell
Push-Location backend
$base = Join-Path (Resolve-Path '..\.pytest-tmp') ('release-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest --basetemp $base
.\.venv\Scripts\python.exe -m ruff check app tests
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
```

Expected: 所有自动化检查通过，冻结应用和安装包完成主流程；若当前沙箱无法读取 Win32 进程信息，只把对应 launcher 测试转到普通用户终端运行，不申请管理员权限。

## Final acceptance checklist

- [ ] 产品名称、应用标识、数据目录、安装包和文档均为“拾要”。
- [ ] 工作区旧版四个数据目录已按批准范围清空并生成新数据库。
- [ ] 源码、依赖、构建产物、设置页和诊断中没有 Codex 接入。
- [ ] OpenAI 兼容与 Anthropic 都能获取模型、手动输入模型并完成能力校验。
- [ ] PDF、PPT/PPTX、DOC/DOCX、TXT、Markdown 符合完整或降级解析规则。
- [ ] 人工选范围与 AI 全文扫描都生成可编辑、可追溯、需确认的重点。
- [ ] 提纲、记忆卡、原题、AI 新题、变式题、错因题和掌握记录可用。
- [ ] 本地精确缓存、模型端提示缓存和可恢复批次行为可观察、可失效。
- [ ] 备份、日志和诊断均不泄露密钥、资料正文或题目正文。
- [ ] 普通用户安装和日常运行不请求管理员权限。
