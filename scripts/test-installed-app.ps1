[CmdletBinding()]
param(
    [string]$Installer = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Installer) { $Installer = Join-Path $root 'release\半导体复习台-0.1.0-beta-Setup.exe' }
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$testRoot = Join-Path $root 'build\installed-smoke'
if (Test-Path -LiteralPath $testRoot) {
    $resolvedBuild = (Resolve-Path (Join-Path $root 'build')).Path
    $resolvedTest = (Resolve-Path -LiteralPath $testRoot).Path
    if (-not $resolvedTest.StartsWith($resolvedBuild, [StringComparison]::OrdinalIgnoreCase)) {
        throw '拒绝清理 build 目录之外的路径。'
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
$installDir = Join-Path $testRoot 'App'
$dataRoot = Join-Path $testRoot 'UserData'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

$install = Start-Process -FilePath $Installer -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', "/DIR=$installDir"
) -PassThru -Wait
if ($install.ExitCode -ne 0) { throw "静默安装失败，退出码：$($install.ExitCode)" }
$executable = Join-Path $installDir 'SemiconductorReview.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw '安装目录中缺少主程序。' }

$oldRoot = $env:SEMIREVIEW_ROOT
$env:SEMIREVIEW_ROOT = $dataRoot
try {
    $application = Start-Process -FilePath $executable -PassThru -WindowStyle Hidden
    $metadataPath = Join-Path $dataRoot 'Runtime\instance.json'
    $deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 250
        if ((Get-Date) -gt $deadline) { throw '安装后的应用未能启动。' }
    } until (Test-Path -LiteralPath $metadataPath)
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$($metadata.port)/ready" -TimeoutSec 5
    if ($ready.status -ne 'ok') { throw '安装后的应用健康检查失败。' }
    New-Item -ItemType Directory -Path (Join-Path $dataRoot 'Data') -Force | Out-Null
    $marker = Join-Path $dataRoot 'Data\keep-after-uninstall.txt'
    Set-Content -LiteralPath $marker -Value 'keep' -Encoding utf8
    $stop = Start-Process -FilePath $executable -ArgumentList '--shutdown' -PassThru -Wait -WindowStyle Hidden
    if ($stop.ExitCode -ne 0) { throw '安装后的应用无法安全退出。' }
    $application.WaitForExit(20 * 1000) | Out-Null

    $uninstaller = Join-Path $installDir 'unins000.exe'
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
    ) -PassThru -Wait
    if ($uninstall.ExitCode -ne 0) { throw "卸载失败，退出码：$($uninstall.ExitCode)" }
    if (-not (Test-Path -LiteralPath $marker)) { throw '卸载错误删除了用户学习数据。' }
    Write-Host '安装、启动、安全退出和保留数据卸载验证通过。'
} finally {
    if ($null -eq $oldRoot) { Remove-Item Env:SEMIREVIEW_ROOT -ErrorAction SilentlyContinue }
    else { $env:SEMIREVIEW_ROOT = $oldRoot }
    if ($application -and -not $application.HasExited) { Stop-Process -Id $application.Id -Force -ErrorAction SilentlyContinue }
}
