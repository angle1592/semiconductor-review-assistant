# Windows Beta Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有半导体复习台制作成无需 Python/Node/管理员权限的 Windows 10/11 x64 安装包，并在公开 GitHub 仓库发布可校验的 `v0.1.0-beta`。

**Architecture:** React 静态资源随 FastAPI 一起进入 PyInstaller `onedir`；桌面入口负责当前用户单实例、动态本地端口、浏览器打开和安全退出；程序与用户数据分离，后者固定在 `%LOCALAPPDATA%\SemiconductorReview`。Inno Setup 负责按用户安装和覆盖升级，GitHub Release 只承载安装包、校验和与用户指南。

**Tech Stack:** Python 3.12、FastAPI、SQLModel/SQLite、PyInstaller、pywin32、React/Vite/TypeScript、Inno Setup 6、PowerShell、pytest、Vitest、Playwright、GitHub CLI。

---

## Task 1: 运行路径、版本和数据库升级保护

**Files:**
- Create: `backend/app/runtime/__init__.py`
- Create: `backend/app/runtime/paths.py`
- Create: `backend/app/runtime/migrations.py`
- Create: `backend/tests/test_runtime_paths.py`
- Create: `backend/tests/test_migrations.py`
- Modify: `backend/app/main.py`

- [ ] 写出失败测试：开发环境尊重 `SEMIREVIEW_DATA_DIR`，打包环境使用 `%LOCALAPPDATA%\SemiconductorReview`，前端资源能从 `_MEIPASS` 或可执行文件目录解析。
- [ ] 实现不可变 `AppPaths`，并统一创建 `Data`、`Backups`、`Logs`、`Runtime` 目录。
- [ ] 写出失败测试：有旧表且 `PRAGMA user_version=0` 时先复制数据库到 `Backups\pre-migration-*`，再迁移到版本 1；空库不产生无意义备份；只保留最近 5 份迁移备份。
- [ ] 实现迁移保护并在 `create_default_app()` 建库前调用。
- [ ] 运行：`..\backend\.venv\Scripts\python.exe -m pytest tests/test_runtime_paths.py tests/test_migrations.py -q`。
- [ ] 提交：`git commit -am "feat: add packaged runtime paths and migration safety"`。

关键接口：

```python
@dataclass(frozen=True)
class AppPaths:
    root: Path
    data: Path
    backups: Path
    logs: Path
    runtime: Path
    frontend_dist: Path

    @classmethod
    def discover(cls) -> "AppPaths": ...
```

## Task 2: 单实例桌面启动器与动态端口

**Files:**
- Create: `backend/app/desktop/__init__.py`
- Create: `backend/app/desktop/instance.py`
- Create: `backend/app/desktop/launcher.py`
- Create: `backend/tests/test_desktop_instance.py`
- Create: `backend/tests/test_desktop_launcher.py`
- Modify: `backend/app/main.py`

- [ ] 写出失败测试：可用端口由操作系统分配；运行元数据包含 PID、端口、应用标识和协议版本；只有 `/ready` 标识完全匹配才视为已有实例。
- [ ] 用 `win32event.CreateMutex` 实现当前用户互斥锁；测试通过注入假锁避免依赖全局 Windows 状态。
- [ ] 实现首实例启动 Uvicorn、写入元数据、等待就绪并打开浏览器；二次启动验证已有实例后只打开浏览器并退出。
- [ ] 实现 `--shutdown`：读取元数据、验证实例、调用本机关闭接口，供安装器升级和卸载前使用。
- [ ] 保证服务只监听 `127.0.0.1`，退出时删除仅属于当前 PID 的元数据。
- [ ] 运行：`..\backend\.venv\Scripts\python.exe -m pytest tests/test_desktop_instance.py tests/test_desktop_launcher.py -q`。
- [ ] 提交：`git commit -am "feat: add Windows desktop launcher"`。

运行元数据固定为：

```json
{"application":"semiconductor-review-assistant","protocol_version":1,"pid":1234,"port":49152}
```

## Task 3: 日志、诊断、文件夹与安全退出 API

**Files:**
- Create: `backend/app/system/__init__.py`
- Create: `backend/app/system/router.py`
- Create: `backend/app/system/service.py`
- Create: `backend/app/system/schemas.py`
- Create: `backend/tests/test_system_api.py`
- Modify: `backend/app/main.py`

- [ ] 写出失败测试：`/api/system/info` 返回版本、打包状态、数据路径与首次配置状态；只允许打开 data/backups/logs；关闭接口只能从回环地址调用。
- [ ] 配置 `RotatingFileHandler(maxBytes=5*1024*1024, backupCount=5)`，日志只记录请求路径、状态和异常类型，不记录请求正文、密钥或课件文本。
- [ ] 实现诊断 ZIP，仅包含版本、能力、路径、最近日志和脱敏配置；明确排除 SQLite、原课件、备份和凭据。
- [ ] 实现打开目录和安全关闭回调；开发模式不允许远程关闭进程。
- [ ] 运行：`..\backend\.venv\Scripts\python.exe -m pytest tests/test_system_api.py -q`。
- [ ] 提交：`git commit -am "feat: add local system diagnostics and shutdown"`。

## Task 4: 首次配置和设置页桌面操作

**Files:**
- Create: `frontend/src/pages/SetupPage.tsx`
- Create: `frontend/src/pages/SetupPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

- [ ] 写出失败测试：未完成 AI 配置时进入简短设置向导；OpenAI 兼容 API 为默认选项；Codex 位于折叠的高级选项中；配置完成后进入首页。
- [ ] 增加 `SystemInfo`、诊断下载、打开目录和退出服务 API 客户端。
- [ ] 在设置页增加“打开数据目录”“打开日志目录”“导出诊断”“退出本地服务”，对危险动作显示明确确认。
- [ ] 保持 API Key 只提交到后端凭据存储，页面不回显已保存密钥。
- [ ] 运行：`npm test -- --run && npm run lint && npm run build`。
- [ ] 提交：`git commit -am "feat: add first-run setup and desktop controls"`。

## Task 5: PyInstaller 可复现构建

**Files:**
- Create: `packaging/desktop_entry.py`
- Create: `packaging/semiconductor-review.spec`
- Create: `scripts/build-windows.ps1`
- Create: `scripts/verify-frozen-app.ps1`
- Modify: `backend/pyproject.toml`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] 在构建依赖中锁定 `pyinstaller>=6.21,<7`，入口只调用 `app.desktop.launcher.main()`。
- [ ] Spec 收集 `frontend/dist`、FastAPI/SQLModel/keyring/PyMuPDF/pywin32/PowerPoint COM/Codex 所需隐藏模块，不打包任何 `data`、日志、备份或密钥。
- [ ] 构建脚本依次执行前端 `npm ci`/测试/构建、后端 pytest、PyInstaller `--clean --noconfirm`，并把结果放入 `release/staging/SemiconductorReview`。
- [ ] 冻结应用验证脚本启动程序、从运行元数据读取动态端口、验证 `/ready`、二次启动、调用 `--shutdown` 并确认进程退出。
- [ ] 运行完整构建和冻结应用验证。
- [ ] 提交：`git commit -am "build: add reproducible Windows bundle"`。

## Task 6: Inno Setup 安装器和覆盖升级

**Files:**
- Create: `packaging/installer.iss`
- Create: `scripts/build-installer.ps1`
- Create: `scripts/test-installed-app.ps1`

- [ ] 安装 Inno Setup 6，并让脚本同时发现 winget 和标准安装路径中的 `ISCC.exe`。
- [ ] 配置 `PrivilegesRequired=lowest`、`ArchitecturesAllowed=x64compatible`、稳定 AppId、`{localappdata}\Programs\SemiconductorReview`、开始菜单和可选桌面快捷方式。
- [ ] 在升级和卸载前调用旧版 `SemiconductorReview.exe --shutdown`；覆盖升级只替换程序文件。
- [ ] 卸载默认保留 `%LOCALAPPDATA%\SemiconductorReview`，卸载末尾单独询问是否删除个人学习数据，默认选择“否”。
- [ ] 构建 `release/半导体复习台-0.1.0-beta-Setup.exe`，静默安装到测试目录并运行端到端健康检查，再卸载并验证个人数据仍在。
- [ ] 提交：`git commit -am "build: add per-user Windows installer"`。

安装器核心设置：

```ini
[Setup]
AppId={{A74E3B83-222F-4C35-B27C-7238356FE5CD}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\SemiconductorReview
OutputBaseFilename=半导体复习台-0.1.0-beta-Setup
Compression=lzma2/ultra64
SolidCompression=yes
```

## Task 7: 安装指南 PDF、校验和与安全扫描

**Files:**
- Create: `docs/user-guide/windows-beta-installation.md`
- Create: `scripts/build-user-guide.py`
- Create: `scripts/prepare-release.ps1`
- Create: `.gitleaks.toml`
- Create: `docs/releases/v0.1.0-beta.md`

- [ ] 编写中文安装指南：系统要求、下载校验、SmartScreen、首次 API 配置、PPT 前提、备份恢复、升级、卸载、日志与问题反馈。
- [ ] 用项目脚本生成 `release/安装与使用说明.pdf`，按 PDF 技能要求渲染检查每一页。
- [ ] 生成安装包 SHA256 文件，格式为 `<64位小写摘要>  <文件名>`。
- [ ] 使用 Gitleaks 扫描工作树和完整 Git 历史；对构建目录再次扫描，并用字符串搜索确认发布物不含用户给出的服务地址、密钥、用户名或绝对开发路径。
- [ ] 在干净临时目录核对 Release 只包含安装器、SHA256、PDF。
- [ ] 提交：`git commit -am "docs: add beta release guide and verification"`。

## Task 8: CI、总体验证、审查与合并

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] Windows CI 运行后端 pytest、前端 Vitest/lint/build，不在 CI 中读取本地 API Key。
- [ ] 本地重新运行后端全量测试、前端测试/lint/build、冻结程序冒烟、安装/覆盖升级/卸载测试和备份恢复测试。
- [ ] 使用 `requesting-code-review` 技能进行独立代码审查，修复高优先级问题并复验。
- [ ] 确认 `git status --short` 只包含计划内变更，发布目录中的二进制不进入 Git 历史。
- [ ] 使用 `finishing-a-development-branch` 技能，将 `codex/windows-beta-distribution` 合并到 `main`。

## Task 9: 创建公开 GitHub 仓库并发布安装包

**External state:**
- Repository: `https://github.com/angle1592/semiconductor-review-assistant`
- Tag: `v0.1.0-beta`
- Release assets: installer, SHA256, PDF guide

- [ ] 在再次确认完整历史无密钥后执行：`gh repo create angle1592/semiconductor-review-assistant --public --source . --remote origin --push`。
- [ ] 推送 `main`，创建并推送带注释标签 `v0.1.0-beta`。
- [ ] 用 `docs/releases/v0.1.0-beta.md` 创建公开非草稿、标记 prerelease 的 GitHub Release，并上传三项资产。
- [ ] 在全新临时目录从 GitHub Release 重新下载三项资产，根据下载的 SHA256 文件校验安装器。
- [ ] 打开公开仓库与 Release 页面，确认源码可见、资产可下载、未发布开发数据或密钥。
- [ ] 最终报告仓库地址、Release 地址、安装器摘要、验证结果和 SmartScreen 未签名提示。

