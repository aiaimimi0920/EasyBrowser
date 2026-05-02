param(
    [string]$ConfigPath = "config.yaml",
    [string]$ServiceEnvOutput = "",
    [switch]$Rebuild,
    [switch]$RenderOnly,
    [switch]$SkipInitConfig
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

$repoRoot = Split-Path -Parent $PSCommandPath
$resolvedConfigPath = Resolve-AbsolutePath -Path $ConfigPath -BaseDir $repoRoot
$resolvedServiceEnvOutput = if ([string]::IsNullOrWhiteSpace($ServiceEnvOutput)) {
    Resolve-AbsolutePath -Path "deploy\service\base\.env.local" -BaseDir $repoRoot
} else {
    Resolve-AbsolutePath -Path $ServiceEnvOutput -BaseDir $repoRoot
}

$initConfigScript = Resolve-AbsolutePath -Path "scripts\init-config.ps1" -BaseDir $repoRoot
$renderScript = Resolve-AbsolutePath -Path "scripts\render-derived-configs.ps1" -BaseDir $repoRoot
$startScript = Resolve-AbsolutePath -Path "scripts\start-service-base.ps1" -BaseDir $repoRoot

if (-not $SkipInitConfig -and -not (Test-Path -LiteralPath $resolvedConfigPath)) {
    & powershell -ExecutionPolicy Bypass -File $initConfigScript
}

if (-not (Test-Path -LiteralPath $resolvedConfigPath)) {
    throw "Missing config file: $resolvedConfigPath"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedServiceEnvOutput) | Out-Null

& powershell -ExecutionPolicy Bypass -File $renderScript `
    -ConfigPath $resolvedConfigPath `
    -ServiceEnvOutput $resolvedServiceEnvOutput

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
