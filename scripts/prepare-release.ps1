[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$release = Join-Path $root 'release'
$installer = Join-Path $release '半导体复习台-0.1.0-beta-Setup.exe'
$guide = Join-Path $release '安装与使用说明.pdf'
$checksum = "$installer.sha256"
$publish = Join-Path $release 'publish'

foreach ($required in @($installer, $guide)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "缺少发布文件：$required" }
}

$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
$line = "$hash  $(Split-Path $installer -Leaf)"
[IO.File]::WriteAllText($checksum, "$line`n", [Text.UTF8Encoding]::new($false))

if (Test-Path -LiteralPath $publish) {
    $resolvedRelease = (Resolve-Path -LiteralPath $release).Path
    $resolvedPublish = (Resolve-Path -LiteralPath $publish).Path
    if (-not $resolvedPublish.StartsWith($resolvedRelease, [StringComparison]::OrdinalIgnoreCase)) {
        throw '拒绝清理 release 目录之外的路径。'
    }
    Remove-Item -LiteralPath $publish -Recurse -Force
}
New-Item -ItemType Directory -Path $publish -Force | Out-Null
Copy-Item -LiteralPath $installer, $checksum, $guide -Destination $publish

$published = @(Get-ChildItem -LiteralPath $publish -File)
if ($published.Count -ne 3) { throw '发布目录必须且只能包含安装器、SHA256 和 PDF。' }
$actual = (Get-FileHash -LiteralPath (Join-Path $publish (Split-Path $installer -Leaf)) -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $hash) { throw '复制后的安装器摘要不一致。' }

Write-Host "发布目录已准备：$publish"
Write-Host "SHA256：$hash"
