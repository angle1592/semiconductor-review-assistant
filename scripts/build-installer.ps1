[CmdletBinding()]
param(
    [string]$IsccPath = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bundle = Join-Path $root 'release\staging\SemiconductorReview\SemiconductorReview.exe'
if (-not (Test-Path -LiteralPath $bundle)) {
    throw '缺少冻结应用目录，请先运行 scripts\build-windows.ps1。'
}

if (-not $IsccPath) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $candidates = @(
        $(if ($command) { $command.Source }),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $IsccPath = $candidates | Select-Object -First 1
}
if (-not $IsccPath) { throw '未找到 Inno Setup 6 的 ISCC.exe。' }
$IsccPath = (Resolve-Path -LiteralPath $IsccPath).Path

& $IsccPath (Join-Path $root 'packaging\installer.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 构建失败，退出码：$LASTEXITCODE" }

$installer = Join-Path $root 'release\SemiconductorReview-0.1.0-beta-Setup.exe'
if (-not (Test-Path -LiteralPath $installer)) { throw '安装器未生成。' }
Write-Host "安装器已生成：$installer"
