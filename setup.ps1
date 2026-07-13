$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'

Write-Host '[1/4] 准备 Python 环境'
if (-not (Test-Path -LiteralPath $Python)) {
    python -m venv (Join-Path $Backend '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw '创建 Python 虚拟环境失败。'
    }
}
& $Python -m ensurepip --upgrade | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw '初始化 pip 失败。'
}

Write-Host '[2/4] 安装后端与 Codex SDK'
Push-Location $Backend
try {
    & $Python -m pip install -e '.[dev,codex]' --index-url 'https://pypi.org/simple'
    if ($LASTEXITCODE -ne 0) {
        throw '安装后端依赖失败。'
    }
} finally {
    Pop-Location
}

Write-Host '[3/4] 安装网页依赖'
Push-Location $Frontend
try {
    npm install --registry='https://registry.npmjs.org'
    if ($LASTEXITCODE -ne 0) {
        throw '安装网页依赖失败。'
    }
    Write-Host '[4/4] 构建网页'
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw '构建网页失败。'
    }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host '安装完成。以后双击或运行 .\start.ps1 即可。' -ForegroundColor Green
