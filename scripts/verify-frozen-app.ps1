[CmdletBinding()]
param(
    [string]$Executable = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Executable) {
    $Executable = Join-Path $root 'release\staging\SemiconductorReview\SemiconductorReview.exe'
}
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$testRoot = Join-Path $root 'build\frozen-smoke-data'
if (Test-Path -LiteralPath $testRoot) {
    $resolvedBuild = (Resolve-Path (Join-Path $root 'build')).Path
    $resolvedTest = (Resolve-Path -LiteralPath $testRoot).Path
    if (-not $resolvedTest.StartsWith($resolvedBuild, [StringComparison]::OrdinalIgnoreCase)) {
        throw '拒绝清理 build 目录之外的路径。'
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

$oldRoot = $env:SEMIREVIEW_ROOT
$env:SEMIREVIEW_ROOT = $testRoot
try {
    $first = Start-Process -FilePath $Executable -PassThru -WindowStyle Hidden
    $metadataPath = Join-Path $testRoot 'Runtime\instance.json'
    $deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 250
        if ((Get-Date) -gt $deadline) { throw '冻结应用未在 45 秒内写入运行元数据。' }
    } until (Test-Path -LiteralPath $metadataPath)

    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    if ($metadata.port -eq 8000) { throw '冻结应用仍然使用固定端口 8000。' }
    $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$($metadata.port)/ready" -TimeoutSec 5
    if ($ready.application -ne 'semiconductor-review-assistant' -or $ready.status -ne 'ok') {
        throw '冻结应用就绪标识不正确。'
    }

    $second = Start-Process -FilePath $Executable -PassThru -WindowStyle Hidden
    $second.WaitForExit(15 * 1000) | Out-Null
    if (-not $second.HasExited -or $second.ExitCode -ne 0) { throw '第二次启动未复用已有实例。' }

    $stop = Start-Process -FilePath $Executable -ArgumentList '--shutdown' -PassThru -WindowStyle Hidden
    $stop.WaitForExit(15 * 1000) | Out-Null
    if (-not $stop.HasExited -or $stop.ExitCode -ne 0) { throw '安全退出命令失败。' }
    $first.WaitForExit(20 * 1000) | Out-Null
    if (-not $first.HasExited) { throw '本地服务未在 20 秒内退出。' }
    Write-Host "冻结应用验证通过，动态端口：$($metadata.port)"
} finally {
    if ($null -eq $oldRoot) { Remove-Item Env:SEMIREVIEW_ROOT -ErrorAction SilentlyContinue }
    else { $env:SEMIREVIEW_ROOT = $oldRoot }
    if ($first -and -not $first.HasExited) { Stop-Process -Id $first.Id -Force -ErrorAction SilentlyContinue }
}
