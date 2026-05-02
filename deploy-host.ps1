param(
    [string]$ConfigPath = "config.yaml",
    [string]$ServiceEnvOutput = "",
    [switch]$Rebuild,
    [switch]$RenderOnly,
    [switch]$SkipInitConfig,
    [string]$RepoOwner = "aiaimimi0920",
    [string]$RepoName = "EasyBrowser",
    [string]$RepoRef = "main",
    [ValidateSet("branch", "tag")]
    [string]$RepoRefKind = "branch",
    [string]$RepoArchiveUrl = "",
    [string]$RepoCacheRoot = "",
    [switch]$ForceRefreshRepo,
    [switch]$ResolveRepoOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$BaseDir
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BaseDir $Path))
}

function Test-RepoLayout {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredRelativePaths
    )

    foreach ($relativePath in $RequiredRelativePaths) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relativePath))) {
            return $false
        }
    }
    return $true
}

function Get-RepoArchiveUrlValue {
    param(
        [string]$Owner,
        [string]$Name,
        [string]$Ref,
        [string]$Kind,
        [string]$ExplicitUrl
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitUrl)) {
        return $ExplicitUrl
    }
    if ($Kind -eq "tag") {
        return "https://codeload.github.com/$Owner/$Name/zip/refs/tags/$Ref"
    }
    return "https://codeload.github.com/$Owner/$Name/zip/refs/heads/$Ref"
}

function Ensure-RepoRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LauncherRoot,
        [Parameter(Mandatory = $true)]
        [string]$Owner,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Ref,
        [Parameter(Mandatory = $true)]
        [string]$RefKind,
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredRelativePaths,
        [string]$ArchiveUrl = "",
        [string]$CacheRoot = "",
        [switch]$ForceRefresh
    )

    if (Test-RepoLayout -Root $LauncherRoot -RequiredRelativePaths $RequiredRelativePaths) {
        return [pscustomobject]@{
            RepoRoot = $LauncherRoot
            Source = "local"
            ArchiveUrl = $null
        }
    }

    $sanitizedRef = ($Ref -replace '[^A-Za-z0-9._-]', '_')
    $resolvedCacheRoot = if ([string]::IsNullOrWhiteSpace($CacheRoot)) {
        Join-Path $LauncherRoot ".repo-cache\$Name-$RefKind-$sanitizedRef"
    } else {
        Resolve-AbsolutePath -Path $CacheRoot -BaseDir $LauncherRoot
    }
    $archiveUrlValue = Get-RepoArchiveUrlValue -Owner $Owner -Name $Name -Ref $Ref -Kind $RefKind -ExplicitUrl $ArchiveUrl
    $repoRoot = Join-Path $resolvedCacheRoot "repo"

    if ($ForceRefresh -and (Test-Path -LiteralPath $resolvedCacheRoot)) {
        Remove-Item -LiteralPath $resolvedCacheRoot -Recurse -Force
    }

    if (-not (Test-RepoLayout -Root $repoRoot -RequiredRelativePaths $RequiredRelativePaths)) {
        New-Item -ItemType Directory -Force -Path $resolvedCacheRoot | Out-Null
        $archivePath = Join-Path $resolvedCacheRoot "$Name-$sanitizedRef.zip"
        $expandedRoot = Join-Path $resolvedCacheRoot "expanded"

        if (Test-Path -LiteralPath $archivePath) {
            Remove-Item -LiteralPath $archivePath -Force
        }
        if (Test-Path -LiteralPath $expandedRoot) {
            Remove-Item -LiteralPath $expandedRoot -Recurse -Force
        }
        if (Test-Path -LiteralPath $repoRoot) {
            Remove-Item -LiteralPath $repoRoot -Recurse -Force
        }

        Write-Host "[deploy-host] downloading repository archive: $archiveUrlValue" -ForegroundColor Cyan
        $previousProgressPreference = $global:ProgressPreference
        $global:ProgressPreference = "SilentlyContinue"
        try {
            Invoke-WebRequest -Uri $archiveUrlValue -OutFile $archivePath
        } finally {
            $global:ProgressPreference = $previousProgressPreference
        }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $expandedRoot -Force

        $extractedRoot = Get-ChildItem -LiteralPath $expandedRoot -Directory | Select-Object -First 1
        if ($null -eq $extractedRoot) {
            throw "Repository archive did not contain an extractable root directory: $archiveUrlValue"
        }

        Move-Item -LiteralPath $extractedRoot.FullName -Destination $repoRoot
    }

    if (-not (Test-RepoLayout -Root $repoRoot -RequiredRelativePaths $RequiredRelativePaths)) {
        throw "Bootstrapped repository root is missing required paths: $repoRoot"
    }

    return [pscustomobject]@{
        RepoRoot = $repoRoot
        Source = "bootstrapped"
        ArchiveUrl = $archiveUrlValue
    }
}

$launcherRoot = Split-Path -Parent $PSCommandPath
$repoInfo = Ensure-RepoRoot `
    -LauncherRoot $launcherRoot `
    -Owner $RepoOwner `
    -Name $RepoName `
    -Ref $RepoRef `
    -RefKind $RepoRefKind `
    -RequiredRelativePaths @("README.md", "scripts\start-service-base.ps1", "scripts\render-derived-configs.ps1") `
    -ArchiveUrl $RepoArchiveUrl `
    -CacheRoot $RepoCacheRoot `
    -ForceRefresh:$ForceRefreshRepo

if ($ResolveRepoOnly) {
    [pscustomobject]@{
        LauncherRoot = $launcherRoot
        RepoRoot = $repoInfo.RepoRoot
        Source = $repoInfo.Source
        ArchiveUrl = $repoInfo.ArchiveUrl
    } | Format-List
    return
}

$repoRoot = $repoInfo.RepoRoot
$resolvedConfigPath = Resolve-AbsolutePath -Path $ConfigPath -BaseDir $launcherRoot
$canonicalServiceEnvOutput = Join-Path $repoRoot "deploy\service\base\.env.local"
$resolvedServiceEnvOutput = if ([string]::IsNullOrWhiteSpace($ServiceEnvOutput)) {
    $canonicalServiceEnvOutput
} else {
    Resolve-AbsolutePath -Path $ServiceEnvOutput -BaseDir $launcherRoot
}

$renderScript = Resolve-AbsolutePath -Path "scripts\render-derived-configs.ps1" -BaseDir $repoRoot
$startScript = Resolve-AbsolutePath -Path "scripts\start-service-base.ps1" -BaseDir $repoRoot
$configExamplePath = Resolve-AbsolutePath -Path "config.example.yaml" -BaseDir $repoRoot

if (-not $SkipInitConfig -and -not (Test-Path -LiteralPath $resolvedConfigPath)) {
    Copy-Item -LiteralPath $configExamplePath -Destination $resolvedConfigPath
    Write-Host "[deploy-host] created config file from template: $resolvedConfigPath" -ForegroundColor Yellow
}

if (-not (Test-Path -LiteralPath $resolvedConfigPath)) {
    throw "Missing config file: $resolvedConfigPath"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedServiceEnvOutput) | Out-Null

& powershell -ExecutionPolicy Bypass -File $renderScript `
    -ConfigPath $resolvedConfigPath `
    -ServiceEnvOutput $resolvedServiceEnvOutput

if ($resolvedServiceEnvOutput -ne $canonicalServiceEnvOutput) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $canonicalServiceEnvOutput) | Out-Null
    Copy-Item -LiteralPath $resolvedServiceEnvOutput -Destination $canonicalServiceEnvOutput -Force
}

if ($RenderOnly) {
    Write-Host "[deploy-host] rendered service env -> $resolvedServiceEnvOutput"
    return
}

$startArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $startScript
)
if ($Rebuild) {
    $startArgs += "-Rebuild"
}

& powershell @startArgs
