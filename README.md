# 拾要

拾要是一款本地优先的总复习工作台。目标是导入 PPT、Word 等复习资料，由使用者直接说明“什么最重要”，或把这套标准交给第三方 AI，用它整理重点并支持后续复习。

## 当前阶段

当前代码处于 Phase 1 基础阶段，只交付以下真实能力：

- 全新的拾要产品身份、本机数据目录与独立数据库；
- 复习项目的新建、查看、编辑和删除；
- 项目内“概览、资料、重点、复习、掌握情况”五步工作区；
- OpenAI 兼容接口的临时基础配置入口；
- 清楚的加载、空状态、失败提示和响应式页面。

以下能力尚未完成，请不要把当前界面中的流程位置当成可用功能：

- 成熟的第三方服务商预设、连接诊断、模型列表获取与模型选择；
- PPT、PPTX、DOC、DOCX 等资料导入和文本/图片提取；
- 由用户规则或 AI 识别重点，以及结果缓存和重新分析；
- 重点确认、题目生成、正式复习和掌握情况统计；
- 新身份下的 Windows 安装包、快捷方式和发布流程。

这些能力会分别在后续 Provider、资料分析、复习与发布阶段接入。

## 开发运行

后端需要 Python 3.12，前端需要 Node.js 与 npm。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd ..\frontend
npm ci
npm run build
cd ..
.\start.ps1
```

本机服务默认打开 `http://127.0.0.1:8000`。停止服务：

```powershell
.\stop.ps1
```

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
cd ..\frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

## 数据与隐私边界

- 项目数据以 SQLite 保存在本机，不包含账户或云同步。
- API Key 使用 Windows 凭据存储，不写入数据库、日志或备份。
- 当前阶段不会上传学习资料，因为资料导入与分析尚未实现。
- 后续只有在用户明确发起分析时，所选资料内容才会发送给当前配置的第三方 AI。
