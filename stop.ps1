[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$RuntimeDir = '',
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path $Root 'data\runtime'
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Backend '.venv\Scripts\python.exe'
}
$PythonPath = [IO.Path]::GetFullPath($PythonPath)
$PidFile = Join-Path $RuntimeDir 'server.pid'
$StopFile = Join-Path $RuntimeDir 'server.stop'
$WorkerPidFile = Join-Path $RuntimeDir 'worker.pid'
$WorkerStopFile = Join-Path $RuntimeDir 'worker.stop'

function Get-VerifiedPythonProcess {
    param([int]$ProcessId)
    $ProcessInfo = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo) {
        return $null
    }
    try {
        $ProcessPath = $ProcessInfo.Path
    } catch {
        return $null
    }
    if (-not [string]::Equals($ProcessPath, $PythonPath, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    return $ProcessInfo
}

function Get-ReviewAssistantReadiness {
    $WebResponse = $null
    try {
        $Request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$Port/ready")
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
        if (
            $Response.status -eq 'ok' -and
            $Response.checks.database -eq 'ok' -and
            $Response.application -eq 'shiyao-review' -and
            $Response.protocol_version -eq 2
        ) {
            return 'current'
        }
        return 'other'
    } catch {
        return 'none'
    } finally {
        if ($null -ne $WebResponse) {
            $WebResponse.Dispose()
        }
    }
}

function Stop-RecordedWorker {
    Set-Content -LiteralPath $WorkerStopFile -Value 'stop' -Encoding Ascii
    if (-not (Test-Path -LiteralPath $WorkerPidFile)) { return }
    $WorkerId = [int](Get-Content -LiteralPath $WorkerPidFile -Raw)
    $Worker = Get-VerifiedPythonProcess $WorkerId
    if ($null -eq $Worker) { return }
    for ($Attempt = 0; $Attempt -lt 50; $Attempt++) {
        if ($null -eq (Get-VerifiedPythonProcess $WorkerId)) { return }
        Start-Sleep -Milliseconds 200
    }
    if ($null -ne (Get-VerifiedPythonProcess $WorkerId)) { Stop-Process -Id $WorkerId -Force -ErrorAction SilentlyContinue }
}

function Get-ListenerProcessId {
    foreach ($Line in netstat -ano -p tcp) {
        if ($Line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            return [int]$Matches[1]
        }
    }
    return $null
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
$ListenerId = Get-ListenerProcessId
if ($null -eq $ListenerId) {
    Stop-RecordedWorker
    Remove-Item -LiteralPath $PidFile, $StopFile, $WorkerPidFile, $WorkerStopFile -Force -ErrorAction SilentlyContinue
    Write-Host "端口 $Port 上没有正在运行的拾要。" -ForegroundColor Yellow
    return
}

$Readiness = Get-ReviewAssistantReadiness
if ($Readiness -ne 'current') {
    throw "端口 $Port 由其他程序占用，停止脚本不会结束它。"
}

$SafeParentId = $null
if (Test-Path -LiteralPath $PidFile) {
    $RecordedId = [int](Get-Content -LiteralPath $PidFile -Raw)
    if ($null -ne (Get-VerifiedPythonProcess $RecordedId)) {
        $SafeParentId = $RecordedId
    }
}

Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding Ascii
Set-Content -LiteralPath $WorkerStopFile -Value 'stop' -Encoding Ascii
for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
    if ($null -eq (Get-ListenerProcessId)) {
        break
    }
    Start-Sleep -Milliseconds 200
}

$RemainingListenerId = Get-ListenerProcessId
if ($null -ne $RemainingListenerId) {
    if ((Get-ReviewAssistantReadiness) -ne 'current') {
        throw "端口 $Port 由其他程序占用，停止脚本不会结束它。"
    }
    Stop-Process -Id $RemainingListenerId -Force
}

if ($null -ne $SafeParentId) {
    for ($Attempt = 0; $Attempt -lt 10; $Attempt++) {
        if ($null -eq (Get-VerifiedPythonProcess $SafeParentId)) {
            break
        }
        Start-Sleep -Milliseconds 100
    }
    if ($null -ne (Get-VerifiedPythonProcess $SafeParentId)) {
        Stop-Process -Id $SafeParentId -Force -ErrorAction SilentlyContinue
    }
}
Stop-RecordedWorker
Remove-Item -LiteralPath $PidFile, $StopFile, $WorkerPidFile, $WorkerStopFile -Force -ErrorAction SilentlyContinue
Write-Host '拾要已停止。' -ForegroundColor Green
}
