param(
    [string]$ConfigPath = "config.yaml",
    [string]$ServiceEnvOutput = "",
    [switch]$NoBuild,
    [switch]$SkipRender,
    [string]$Image = "",
    [switch]$Pull,
    [string]$ContainerName = "",
    [int]$HostPort = 0,
    [string]$NetworkName = "EasyAiMi",
    [string]$NetworkAlias = "easy-browser",
    [string]$ComposeProjectName = ""
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

function Ensure-DockerNetwork {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return
    }

    & docker network inspect $Name *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "Creating docker network: $Name" -ForegroundColor Cyan
    & docker network create $Name
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create docker network $Name"
    }
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $prefix = "$Name="
    $lines = if (Test-Path -LiteralPath $Path) {
        Get-Content -LiteralPath $Path
    } else {
        @()
    }
    $updated = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index].StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $lines[$index] = "$prefix$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines += "$prefix$Value"
    }
    Set-Content -LiteralPath $Path -Value $lines
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedConfigPath = Resolve-AbsolutePath -Path $ConfigPath -BaseDir $repoRoot
$composeFile = Resolve-AbsolutePath -Path "deploy\service\base\docker-compose.yaml" -BaseDir $repoRoot
$serviceEnvPath = if ([string]::IsNullOrWhiteSpace($ServiceEnvOutput)) {
    Resolve-AbsolutePath -Path "deploy\service\base\.env.local" -BaseDir $repoRoot
} else {
    Resolve-AbsolutePath -Path $ServiceEnvOutput -BaseDir $repoRoot
}
$renderScript = Resolve-AbsolutePath -Path "scripts\render-derived-configs.ps1" -BaseDir $repoRoot

if (-not $SkipRender) {
    & powershell -ExecutionPolicy Bypass -File $renderScript `
        -ConfigPath $resolvedConfigPath `
        -ServiceEnvOutput $serviceEnvPath
}

if (-not (Test-Path -LiteralPath $serviceEnvPath)) {
    throw "Missing rendered runtime env: $serviceEnvPath"
}

if ($Image -and $Pull) {
    Write-Host "Pulling service image: $Image" -ForegroundColor Cyan
    & docker pull $Image
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull docker image: $Image"
    }
}

$resolvedContainerName = if ([string]::IsNullOrWhiteSpace($ContainerName)) {
    "easy-browser"
} else {
    $ContainerName
}
$resolvedHostPort = if ($HostPort -gt 0) { $HostPort } else { 18080 }
$resolvedComposeProjectName = if ([string]::IsNullOrWhiteSpace($ComposeProjectName)) {
    "easy-browser"
} else {
    $ComposeProjectName
}

if (-not [string]::IsNullOrWhiteSpace($Image)) {
    $env:EASYBROWSER_SERVICE_IMAGE = $Image
}
$env:EASYBROWSER_SERVICE_CONTAINER_NAME = $resolvedContainerName
$env:EASYBROWSER_SERVICE_HOST_PORT = [string]$resolvedHostPort
$env:EASYBROWSER_SERVICE_ENV_FILE = $serviceEnvPath
$env:EASYBROWSER_SERVICE_NETWORK = $NetworkName
$env:EASYBROWSER_SERVICE_NETWORK_ALIAS = $NetworkAlias

Set-DotEnvValue -Path $serviceEnvPath -Name "EASYBROWSER_LISTEN" -Value "0.0.0.0:18080"

Ensure-DockerNetwork -Name $NetworkName

$args = @("compose", "-p", $resolvedComposeProjectName, "-f", $composeFile, "up", "-d")
if (-not $NoBuild -and [string]::IsNullOrWhiteSpace($Image)) {
    $args += "--build"
}

Write-Host "Starting EasyBrowser service/base via Docker Compose..." -ForegroundColor Cyan
& docker @args
if ($LASTEXITCODE -ne 0) {
    throw "docker compose failed with exit code $LASTEXITCODE"
}

Write-Host "EasyBrowser service/base deployment finished." -ForegroundColor Green
Write-Host ("Container name: " + $resolvedContainerName)
Write-Host ("Base URL: http://127.0.0.1:{0}" -f $resolvedHostPort)
Write-Host ("Network alias: " + $NetworkAlias)
