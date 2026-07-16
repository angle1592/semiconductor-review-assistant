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
$FrontendDist = if ([string]::IsNullOrWhiteSpace($env:SHIYAO_FRONTEND_DIST)) {
    Join-Path $Root 'frontend\dist'
} else {
    $env:SHIYAO_FRONTEND_DIST
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

function Get-ReviewAssistantReadiness {
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
        if ($Response.status -ne 'ok' -or $Response.checks.database -ne 'ok') {
            return 'none'
        }
        if (
            $Response.application -eq 'shiyao-review' -and
            $Response.protocol_version -eq 2
        ) {
            return 'current'
        }
        return 'legacy'
    } catch {
        return 'none'
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

function Get-ListenerProcessId {
    foreach ($Line in netstat -ano -p tcp) {
        if ($Line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            return [int]$Matches[1]
        }
    }
    return $null
}

function Test-VerifiedRunnerListener {
    $ListenerId = Get-ListenerProcessId
    if ($null -eq $ListenerId) {
        return $false
    }
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ListenerId" -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo -or [string]::IsNullOrWhiteSpace($ProcessInfo.CommandLine)) {
        return $false
    }
    $HasPythonPath = $ProcessInfo.CommandLine.IndexOf(
        $PythonPath,
        [StringComparison]::OrdinalIgnoreCase
    ) -ge 0
    return $HasPythonPath -and $ProcessInfo.CommandLine -like '*-m app.runner*'
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

function Invoke-WithLauncherMutex {
    param([scriptblock]$Action)

    $Identity = "$([System.IO.Path]::GetFullPath($Root).ToLowerInvariant())|$Port"
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $HashBytes = $Hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Identity))
    } finally {
        $Hasher.Dispose()
    }
    $Hash = [System.BitConverter]::ToString($HashBytes).Replace('-', '')
    $Mutex = [System.Threading.Mutex]::new($false, "Local\Shiyao-$Hash")
    $Acquired = $false
    try {
        try {
            $Acquired = $Mutex.WaitOne(120000)
        } catch [System.Threading.AbandonedMutexException] {
            $Acquired = $true
        }
        if (-not $Acquired) {
            throw '另一个启动或停止操作长时间未完成，请稍后重试。'
        }
        & $Action
    } finally {
        if ($Acquired) {
            $Mutex.ReleaseMutex()
        }
        $Mutex.Dispose()
    }
}

Invoke-WithLauncherMutex {
$Readiness = Get-ReviewAssistantReadiness
if ($Readiness -eq 'current' -or ($Readiness -eq 'legacy' -and (Test-VerifiedRunnerListener))) {
    if (-not $NoBrowser) {
        Start-Process $Url
    }
    Write-Host "拾要已在运行，已重新打开：$Url" -ForegroundColor Green
    return
}

if (Test-LauncherPortInUse) {
    throw "端口 $Port 已被其他程序占用，且该程序不是可用的复习台。"
}

if (-not (Test-Path -LiteralPath $PythonPath) -or -not (Test-Path -LiteralPath $FrontendIndex)) {
    Write-Host '检测到尚未完成安装，先运行初始化。' -ForegroundColor Yellow
    & $Setup
    if (-not (Test-Path -LiteralPath $PythonPath) -or -not (Test-Path -LiteralPath $FrontendIndex)) {
        throw '初始化未生成完整的 Python 环境或网页文件，请重新运行 setup.ps1 查看错误。'
    }
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
$PidFile = Join-Path $RuntimeDir 'server.pid'
$StopFile = Join-Path $RuntimeDir 'server.stop'
$WorkerPidFile = Join-Path $RuntimeDir 'worker.pid'
$WorkerStopFile = Join-Path $RuntimeDir 'worker.stop'
$OutputLog = Join-Path $RuntimeDir 'server.stdout.log'
$ErrorLog = Join-Path $RuntimeDir 'server.stderr.log'
$WorkerOutputLog = Join-Path $RuntimeDir 'worker.stdout.log'
$WorkerErrorLog = Join-Path $RuntimeDir 'worker.stderr.log'
Remove-Item -LiteralPath $PidFile, $StopFile, $WorkerPidFile, $WorkerStopFile -Force -ErrorAction SilentlyContinue

$HadStopFile = Test-Path Env:SHIYAO_STOP_FILE
$PreviousStopFile = $env:SHIYAO_STOP_FILE
$HadPort = Test-Path Env:SHIYAO_PORT
$PreviousPort = $env:SHIYAO_PORT
$HadWorkerStopFile = Test-Path Env:SHIYAO_WORKER_STOP_FILE
$PreviousWorkerStopFile = $env:SHIYAO_WORKER_STOP_FILE
$Server = $null
$Worker = $null

try {
    $env:SHIYAO_STOP_FILE = $StopFile
    $env:SHIYAO_PORT = [string]$Port
    $env:SHIYAO_WORKER_STOP_FILE = $WorkerStopFile
    $Server = Start-Process -FilePath $PythonPath `
        -ArgumentList @('-m', 'app.runner') `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutputLog `
        -RedirectStandardError $ErrorLog `
        -PassThru
    $Worker = Start-Process -FilePath $PythonPath `
        -ArgumentList @('-m', 'app.jobs.worker') `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput $WorkerOutputLog `
        -RedirectStandardError $WorkerErrorLog `
        -PassThru
} finally {
    Restore-EnvironmentValue 'SHIYAO_STOP_FILE' $HadStopFile $PreviousStopFile
    Restore-EnvironmentValue 'SHIYAO_PORT' $HadPort $PreviousPort
    Restore-EnvironmentValue 'SHIYAO_WORKER_STOP_FILE' $HadWorkerStopFile $PreviousWorkerStopFile
}

Set-Content -LiteralPath $PidFile -Value $Server.Id -Encoding Ascii
Set-Content -LiteralPath $WorkerPidFile -Value $Worker.Id -Encoding Ascii

$Ready = $false
for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
    Start-Sleep -Milliseconds 250
    if ($Server.HasExited) {
        break
    }
    if ((Get-ReviewAssistantReadiness) -eq 'current') {
        $Ready = $true
        break
    }
}

if (-not $Ready) {
    Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding Ascii
    Set-Content -LiteralPath $WorkerStopFile -Value 'stop' -Encoding Ascii
    if (-not $Server.HasExited -and -not $Server.WaitForExit(5000)) {
        Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
    }
    if ($Worker -and -not $Worker.HasExited -and -not $Worker.WaitForExit(5000)) {
        Stop-Process -Id $Worker.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile, $StopFile, $WorkerPidFile, $WorkerStopFile -Force -ErrorAction SilentlyContinue
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
Write-Host "拾要已启动：$Url" -ForegroundColor Green
}
