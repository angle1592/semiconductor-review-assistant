[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$RuntimeDir = '',
    [string]$PythonPath = '',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$FrontendDist = if ([string]::IsNullOrWhiteSpace($env:SEMIREVIEW_FRONTEND_DIST)) {
    Join-Path $Root 'frontend\dist'
} else {
    $env:SEMIREVIEW_FRONTEND_DIST
}
$FrontendIndex = Join-Path $FrontendDist 'index.html'
$Setup = Join-Path $Root 'setup.ps1'
$Url = "http://127.0.0.1:$Port"
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path $Root 'data\runtime'
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Backend '.venv\Scripts\python.exe'
}

function Test-ReviewAssistantReady {
    $WebResponse = $null
    try {
        $Request = [System.Net.HttpWebRequest]::Create("$Url/ready")
        $Request.Proxy = $null
        $Request.Timeout = 1000
        $Request.ReadWriteTimeout = 1000
        $WebResponse = $Request.GetResponse()
        $Reader = New-Object System.IO.StreamReader($WebResponse.GetResponseStream())
        try {
            $Response = ($Reader.ReadToEnd() | ConvertFrom-Json)
        } finally {
            $Reader.Dispose()
        }
        return $Response.status -eq 'ok' -and $Response.checks.database -eq 'ok'
    } catch {
        return $false
    } finally {
        if ($null -ne $WebResponse) {
            $WebResponse.Dispose()
        }
    }
}

function Test-LauncherPortInUse {
    return [bool]([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        Where-Object { $_.Port -eq $Port })
}

function Restore-EnvironmentValue {
    param(
        [string]$Name,
        [bool]$Existed,
        [string]$Value
    )
    if ($Existed) {
        Set-Item -Path "Env:$Name" -Value $Value
    } else {
        Remove-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
    }
}

if (Test-ReviewAssistantReady) {
    if (-not $NoBrowser) {
        Start-Process $Url
    }
    Write-Host "半导体复习台已在运行，已重新打开：$Url" -ForegroundColor Green
    return
}

if (Test-LauncherPortInUse) {
    throw "端口 $Port 已被其他程序占用，且该程序不是可用的复习台。"
}

if (-not (Test-Path -LiteralPath $PythonPath) -or -not (Test-Path -LiteralPath $FrontendIndex)) {
    Write-Host '检测到尚未完成安装，先运行初始化。' -ForegroundColor Yellow
    & $Setup
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
$PidFile = Join-Path $RuntimeDir 'server.pid'
$StopFile = Join-Path $RuntimeDir 'server.stop'
$OutputLog = Join-Path $RuntimeDir 'server.stdout.log'
$ErrorLog = Join-Path $RuntimeDir 'server.stderr.log'
Remove-Item -LiteralPath $PidFile, $StopFile -Force -ErrorAction SilentlyContinue

$HadStopFile = Test-Path Env:SEMIREVIEW_STOP_FILE
$PreviousStopFile = $env:SEMIREVIEW_STOP_FILE
$HadPort = Test-Path Env:SEMIREVIEW_PORT
$PreviousPort = $env:SEMIREVIEW_PORT
$Server = $null

try {
    $env:SEMIREVIEW_STOP_FILE = $StopFile
    $env:SEMIREVIEW_PORT = [string]$Port
    $Server = Start-Process -FilePath $PythonPath `
        -ArgumentList @('-m', 'app.runner') `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutputLog `
        -RedirectStandardError $ErrorLog `
        -PassThru
} finally {
    Restore-EnvironmentValue 'SEMIREVIEW_STOP_FILE' $HadStopFile $PreviousStopFile
    Restore-EnvironmentValue 'SEMIREVIEW_PORT' $HadPort $PreviousPort
}

Set-Content -LiteralPath $PidFile -Value $Server.Id -Encoding Ascii

$Ready = $false
for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
    Start-Sleep -Milliseconds 250
    if (Test-ReviewAssistantReady) {
        $Ready = $true
        break
    }
    if ($Server.HasExited) {
        break
    }
}

if (-not $Ready) {
    Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding Ascii
    if (-not $Server.HasExited -and -not $Server.WaitForExit(5000)) {
        Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile, $StopFile -Force -ErrorAction SilentlyContinue
    $Details = ''
    if (Test-Path -LiteralPath $ErrorLog) {
        $Details = (Get-Content -LiteralPath $ErrorLog -Tail 8) -join [Environment]::NewLine
    }
    if ($Details) {
        throw "本地服务未能启动。`n$Details"
    }
    throw '本地服务未能启动。请检查后台日志。'
}

if (-not $NoBrowser) {
    Start-Process $Url
}
Write-Host "半导体复习台已启动：$Url" -ForegroundColor Green
