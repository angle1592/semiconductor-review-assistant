[CmdletBinding()]
param(
    [string]$ShortcutPath = '',
    [string]$StartScript = ''
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($StartScript)) {
    $StartScript = Join-Path $Root 'start.ps1'
}
$StartScript = [System.IO.Path]::GetFullPath($StartScript)
if (-not (Test-Path -LiteralPath $StartScript -PathType Leaf)) {
    throw "找不到启动脚本：$StartScript"
}

if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
    $Desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    $ShortcutPath = Join-Path $Desktop '半导体复习台.lnk'
}
$ShortcutPath = [System.IO.Path]::GetFullPath($ShortcutPath)
$ShortcutDirectory = Split-Path -Parent $ShortcutPath
New-Item -ItemType Directory -Path $ShortcutDirectory -Force | Out-Null

$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PowerShell
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""
$Shortcut.WorkingDirectory = Split-Path -Parent $StartScript
$Shortcut.Description = '打开半导体课后复习助手'
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
$Shortcut.Save()

Write-Host "桌面快捷方式已创建：$ShortcutPath" -ForegroundColor Green
