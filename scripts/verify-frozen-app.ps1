[CmdletBinding()]
param(
    [string]$Executable = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Executable) {
    $Executable = Join-Path $root 'release\staging\Shiyao\Shiyao.exe'
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

$oldRoot = $env:SHIYAO_ROOT
$env:SHIYAO_ROOT = $testRoot
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
    if ($ready.application -ne 'shiyao-review' -or $ready.status -ne 'ok') {
        throw '冻结应用就绪标识不正确。'
    }

    if (-not $metadata.worker_pid) { throw '冻结应用未记录后台任务进程。' }
    $worker = Get-Process -Id $metadata.worker_pid -ErrorAction SilentlyContinue
    if (-not $worker) { throw '冻结应用后台任务进程未运行。' }

    $project = Invoke-RestMethod -Uri "http://127.0.0.1:$($metadata.port)/api/projects" `
        -Method Post -ContentType 'application/json' `
        -Body '{"name":"冻结验证项目","description":"发布前验证","importance_prompt":"优先提取定义"}'
    $pdfPath = Join-Path $testRoot 'smoke.pdf'
    $pdfBase64 = 'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDIwMCAxMjBdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDY1Pj4Kc3RyZWFtCgpxCkJUCjEgMCAwIDEgMjAgNzAgVG0KL2hlbHYgMTEgVGYgWzw2NDY1NmM2NTc0NjUyMDZkNjU+XVRKCkVUClEKCmVuZHN0cmVhbQplbmRvYmoKCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAwMTIwIDAwMDAwIG4gCjAwMDAwMDAxNzIgMDAwMDAgbiAKMDAwMDAwMDIxMyAwMDAwMCBuIAowMDAwMDAzMjAgMDAwMDAgbiAKMDAwMDAwMDQwOSAwMDAwMCBuIAoKdHJhaWxlcgo8PC9TaXplIDcvUm9vdCAxIDAgUi9JRFs8QzNBNjZCQzM5OUMyQjRDMkI3NEQyODAxMTFDMkJGQzM+PEJBRUM1N0Y4RjlENEI4OTA1MTQ4QzkxN0ZBQTRFQTk1Pl0+PgpzdGFydHhyZWYKNTIyCiUlRU9GCg=='
    [IO.File]::WriteAllBytes($pdfPath, [Convert]::FromBase64String($pdfBase64))
    $uploadJson = & curl.exe -sS -f -X POST -F "file=@$pdfPath;type=application/pdf" `
        -F 'source_kind=mixed' `
        "http://127.0.0.1:$($metadata.port)/api/projects/$($project.id)/sources"
    if ($LASTEXITCODE -ne 0) { throw '冻结应用 PDF 导入失败。' }
    $document = $uploadJson | ConvertFrom-Json
    if ($document.page_count -ne 1) { throw '冻结应用 PDF 页码解析不正确。' }

    $backupPath = Join-Path $testRoot 'smoke-backup.zip'
    Invoke-WebRequest -Uri "http://127.0.0.1:$($metadata.port)/api/backups/export" -OutFile $backupPath -TimeoutSec 20
    if ((Get-Item -LiteralPath $backupPath).Length -lt 100) { throw '冻结应用备份导出为空。' }

    $second = Start-Process -FilePath $Executable -PassThru -WindowStyle Hidden
    $second.WaitForExit(15 * 1000) | Out-Null
    if (-not $second.HasExited -or $second.ExitCode -ne 0) { throw '第二次启动未复用已有实例。' }

    $stop = Start-Process -FilePath $Executable -ArgumentList '--shutdown' -PassThru -WindowStyle Hidden
    $stop.WaitForExit(15 * 1000) | Out-Null
    if (-not $stop.HasExited -or $stop.ExitCode -ne 0) { throw '安全退出命令失败。' }
    $first.WaitForExit(20 * 1000) | Out-Null
    if (-not $first.HasExited) { throw '本地服务未在 20 秒内退出。' }
    Start-Sleep -Milliseconds 500
    if (Get-Process -Id $metadata.worker_pid -ErrorAction SilentlyContinue) {
        throw '安全退出后后台任务进程仍在运行。'
    }
    if (Test-Path -LiteralPath $metadataPath) { throw '安全退出后仍残留运行元数据。' }
    Write-Host "冻结应用验证通过，动态端口：$($metadata.port)"
} finally {
    if ($null -eq $oldRoot) { Remove-Item Env:SHIYAO_ROOT -ErrorAction SilentlyContinue }
    else { $env:SHIYAO_ROOT = $oldRoot }
    if ($first -and -not $first.HasExited) { Stop-Process -Id $first.Id -Force -ErrorAction SilentlyContinue }
}
