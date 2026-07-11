$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'
$FrontendIndex = Join-Path $Root 'frontend\dist\index.html'
$Setup = Join-Path $Root 'setup.ps1'
$Url = 'http://127.0.0.1:8000'
$StopFile = Join-Path ([System.IO.Path]::GetTempPath()) "semireview-stop-$PID-$([guid]::NewGuid().ToString('N'))"
$PreviousStopFile = $env:SEMIREVIEW_STOP_FILE

if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $FrontendIndex)) {
    Write-Host '检测到尚未完成安装，先运行初始化。' -ForegroundColor Yellow
    & $Setup
}

$PortInUse = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq 8000 }
if ($PortInUse) {
    throw '端口 8000 已被其他程序占用。请先关闭旧的复习台或占用该端口的程序。'
}

$Server = $null
try {
    $env:SEMIREVIEW_STOP_FILE = $StopFile
    $Server = Start-Process -FilePath $Python `
        -ArgumentList @('-m', 'app.runner') `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -PassThru
    if ($null -eq $PreviousStopFile) {
        Remove-Item Env:SEMIREVIEW_STOP_FILE
    } else {
        $env:SEMIREVIEW_STOP_FILE = $PreviousStopFile
    }

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        Start-Sleep -Milliseconds 300
        if ($Server.HasExited) { break }
        try {
            $Response = Invoke-WebRequest -UseBasicParsing "$Url/ready" -TimeoutSec 1
            if ($Response.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        } catch {
            # The service may still be starting.
        }
    }

    if (-not $Ready) {
        throw '本地服务未能启动。请在 backend 目录运行 uvicorn 查看详细错误。'
    }

    Start-Process $Url
    Write-Host "半导体复习台已启动：$Url" -ForegroundColor Green
    Write-Host '按 Enter 停止本地服务。'
    Read-Host | Out-Null
} finally {
    if ($null -ne $Server -and -not $Server.HasExited) {
        Set-Content -LiteralPath $StopFile -Value 'stop'
        if (-not $Server.WaitForExit(5000)) {
            Stop-Process -Id $Server.Id -Force
        }
    }
    Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue
    if ($null -eq $PreviousStopFile) {
        Remove-Item Env:SEMIREVIEW_STOP_FILE -ErrorAction SilentlyContinue
    } else {
        $env:SEMIREVIEW_STOP_FILE = $PreviousStopFile
    }
}
