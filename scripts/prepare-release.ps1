[CmdletBinding()]
param(
    [string]$GitleaksPath = '',
    [string[]]$ForbiddenPatterns = @()
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$release = Join-Path $root 'release'
$installer = Join-Path $release '半导体复习台-0.1.0-beta-Setup.exe'
$guide = Join-Path $release '安装与使用说明.pdf'
$checksum = "$installer.sha256"
$publish = Join-Path $release 'publish'
$staging = Join-Path $release 'staging\SemiconductorReview'
$config = Join-Path $root '.gitleaks.toml'
$securityRoot = Join-Path $root 'build\security-source'
$securityArchive = Join-Path $root 'build\security-source.zip'
$userProfilePattern = [Regex]::Escape([Environment]::GetFolderPath('UserProfile'))
$builtInSecretPatterns = @(
    'sk-[A-Za-z0-9]{20,}',
    'sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}'
)
$effectiveForbiddenPatterns = $builtInSecretPatterns + @($ForbiddenPatterns) + @($userProfilePattern)

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step 失败，退出码：$LASTEXITCODE" }
}

function Resolve-Gitleaks() {
    if ($GitleaksPath) { return (Resolve-Path -LiteralPath $GitleaksPath).Path }
    $command = Get-Command gitleaks.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidate = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\gitleaks.exe'
    if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    throw '未找到 gitleaks。请先安装后再准备公开发布。'
}

$workingChanges = @(git -C $root status --porcelain --untracked-files=all)
Assert-NativeSuccess '检查 Git 状态'
if ($workingChanges.Count -gt 0) {
    throw '公开发布前工作树必须干净；请先提交所有源代码和测试改动。'
}
$gitleaks = Resolve-Gitleaks

foreach ($required in @($installer, $guide, $staging)) {
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

& $gitleaks git --config $config --redact --exit-code 1 $root
Assert-NativeSuccess 'Git 历史密钥扫描'

foreach ($target in @($securityRoot, $securityArchive)) {
    if (Test-Path -LiteralPath $target) {
        $resolvedBuild = (Resolve-Path (Join-Path $root 'build')).Path
        $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
        if (-not $resolvedTarget.StartsWith($resolvedBuild, [StringComparison]::OrdinalIgnoreCase)) {
            throw '拒绝清理 build 目录之外的安全扫描临时路径。'
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
New-Item -ItemType Directory -Path (Split-Path $securityArchive) -Force | Out-Null
git -C $root archive --format=zip --output=$securityArchive HEAD
Assert-NativeSuccess '导出待发布源代码'
Expand-Archive -LiteralPath $securityArchive -DestinationPath $securityRoot

& $gitleaks dir --config $config --redact --max-archive-depth 2 --exit-code 1 $securityRoot
Assert-NativeSuccess '源代码快照密钥扫描'
& $gitleaks dir --config $config --redact --max-archive-depth 2 --exit-code 1 $publish
Assert-NativeSuccess '发布文件密钥扫描'
& $gitleaks dir --config $config --redact --max-archive-depth 2 --exit-code 1 $staging
Assert-NativeSuccess '未压缩程序目录密钥扫描'

$rg = Get-Command rg.exe -ErrorAction SilentlyContinue
if (-not $rg) { throw '未找到 rg.exe，无法执行发布文件隐私模式扫描。' }
& $rg.Source -a -n -i -- ($effectiveForbiddenPatterns -join '|') $publish $staging
if ($LASTEXITCODE -eq 0) { throw '发布文件包含禁止公开的密钥、私有域名或本机绝对路径。' }
if ($LASTEXITCODE -ne 1) { throw "发布文件隐私模式扫描失败，退出码：$LASTEXITCODE" }

Write-Host "发布目录已准备：$publish"
Write-Host "SHA256：$hash"
Write-Host 'Git 历史、源代码快照和发布文件安全扫描通过。'
