# 回片：半导体课后复习台

一个本地优先的课后复习助手：导入培训课件，选择当天页面，用 10～15 分钟完成主动回忆、纠错、自评和间隔复习。

## Windows 快速开始

首次运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

以后启动：

```powershell
.\start.ps1
```

启动脚本会在后台运行本地服务并打开 `http://127.0.0.1:8000`。按 Enter 可停止服务。
如果端口 8000 已被旧实例占用，脚本会明确提示；正常停止时会先让服务释放 SQLite 再退出。

## 使用顺序

1. 在“课程”中新建课程。
2. 进入课程，上传 PDF、PPT 或 PPTX；PPT需要本机安装 Microsoft PowerPoint。
3. 在“设置”中选择 OpenAI兼容 API或 Codex SDK，并测试连接。
4. 从课程页选择课件，记录当天页面和课堂重点。
5. 生成题目后进入十分钟复习；坏题和跳过题不会影响掌握度。
6. 定期从“设置”导出不含 API Key的 ZIP备份。

## 数据与隐私

- 正式数据保存在项目根目录的 `data/`，SQLite是唯一主数据。
- OpenAI兼容 API Key保存在 Windows凭据存储中，不进入数据库或备份。
- 只有你选中的课件页面、提取文字和课堂补充会发送给当前 AI后端。
- 两个 AI后端只会手动切换，失败时不会自动转发。

## 开发命令

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

前端：

```powershell
cd frontend
npm test
npm run build
npm run lint
npm run test:e2e
```

浏览器端到端测试默认使用本机已安装的 Google Chrome，不额外下载浏览器。

## 第一版边界

不包含账户系统、双向云同步、手机写入、OCR、自动控制 NotebookLM、排行榜或完整半导体百科。NotebookLM内容通过 Markdown/TXT原文导入。
