[CmdletBinding()]
param(
    [string]$PythonPath = '',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontend = Join-Path $root 'frontend'
$backend = Join-Path $root 'backend'
$buildRoot = Join-Path $root 'build\pyinstaller'
$staging = Join-Path $root 'release\staging\SemiconductorReview'

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step 失败，退出码：$LASTEXITCODE" }
}

if (-not $PythonPath) {
    $candidate = Join-Path $backend '.build-venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $candidate)) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $launcher) { throw '未找到 Python 3.11 或更高版本。' }
        & $launcher.Source -3 -m venv (Join-Path $backend '.build-venv')
    }
    $PythonPath = $candidate
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path

Push-Location $frontend
try {
    npm ci
    Assert-NativeSuccess 'npm ci'
    if (-not $SkipTests) {
        npm test -- --run
        Assert-NativeSuccess '前端测试'
        npm run lint
        Assert-NativeSuccess '前端 Lint'
    }
    npm run build
    Assert-NativeSuccess '前端构建'
} finally {
    Pop-Location
}

& $PythonPath -m pip install --disable-pip-version-check -e "$backend[build,dev]"
Assert-NativeSuccess 'Python 构建依赖安装'
if (-not $SkipTests) {
    $pytestTemp = Join-Path $root 'build\pytest-tmp'
    New-Item -ItemType Directory -Path (Split-Path $pytestTemp) -Force | Out-Null
    & $PythonPath -m pytest (Join-Path $backend 'tests') -q --basetemp $pytestTemp
    Assert-NativeSuccess '后端测试'
}

& $PythonPath -m PyInstaller `
    --clean `
    --noconfirm `
    --workpath (Join-Path $buildRoot 'work') `
    --distpath (Join-Path $buildRoot 'dist') `
    (Join-Path $root 'packaging\semiconductor-review.spec')
Assert-NativeSuccess 'PyInstaller 构建'

$bundle = Join-Path $buildRoot 'dist\SemiconductorReview'
if (-not (Test-Path -LiteralPath (Join-Path $bundle 'SemiconductorReview.exe'))) {
    throw 'PyInstaller 未生成 SemiconductorReview.exe。'
}
if (Test-Path -LiteralPath $staging) {
    $resolvedRelease = (Resolve-Path (Join-Path $root 'release')).Path
    $resolvedStaging = (Resolve-Path -LiteralPath $staging).Path
    if (-not $resolvedStaging.StartsWith($resolvedRelease, [StringComparison]::OrdinalIgnoreCase)) {
        throw '拒绝清理 release 目录之外的路径。'
    }
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path $staging) -Force | Out-Null
Copy-Item -LiteralPath $bundle -Destination $staging -Recurse
Write-Host "Windows 应用目录已生成：$staging"
