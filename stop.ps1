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
$PidFile = Join-Path $RuntimeDir 'server.pid'
$StopFile = Join-Path $RuntimeDir 'server.stop'

function Get-VerifiedRunnerProcess {
    param([int]$ProcessId)
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo -or [string]::IsNullOrWhiteSpace($ProcessInfo.CommandLine)) {
        return $null
    }
    $HasPythonPath = $ProcessInfo.CommandLine.IndexOf(
        $PythonPath,
        [StringComparison]::OrdinalIgnoreCase
    ) -ge 0
    if (-not $HasPythonPath -or $ProcessInfo.CommandLine -notlike '*-m app.runner*') {
        return $null
    }
    return $ProcessInfo
}

function Get-ListenerProcessId {
    foreach ($Line in netstat -ano -p tcp) {
        if ($Line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            return [int]$Matches[1]
        }
    }
    return $null
}

$LauncherId = $null
if (Test-Path -LiteralPath $PidFile) {
    $ParsedId = 0
    if ([int]::TryParse((Get-Content -LiteralPath $PidFile -Raw).Trim(), [ref]$ParsedId)) {
        if ($null -ne (Get-VerifiedRunnerProcess $ParsedId)) {
            $LauncherId = $ParsedId
        }
    }
}

if ($null -ne $LauncherId) {
    Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding Ascii
    try {
        $Launcher = [System.Diagnostics.Process]::GetProcessById($LauncherId)
        $null = $Launcher.WaitForExit(8000)
    } catch {
        # The process may have exited between validation and waiting.
    }
}

for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
    if ($null -eq (Get-ListenerProcessId)) {
        break
    }
    Start-Sleep -Milliseconds 200
}

$ListenerId = Get-ListenerProcessId
if ($null -ne $ListenerId) {
    $Listener = Get-VerifiedRunnerProcess $ListenerId
    if ($null -eq $Listener) {
        throw "端口 $Port 由其他程序占用，停止脚本不会结束它。"
    }
    Stop-Process -Id $ListenerId -Force
    $Parent = Get-VerifiedRunnerProcess $Listener.ParentProcessId
    if ($null -ne $Parent) {
        Stop-Process -Id $Parent.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if ($null -ne $LauncherId) {
    Stop-Process -Id $LauncherId -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $PidFile, $StopFile -Force -ErrorAction SilentlyContinue
Write-Host '半导体复习台已停止。' -ForegroundColor Green

