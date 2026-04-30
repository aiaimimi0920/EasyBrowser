param(
    [string]$OutputPath = 'deploy/service/base/bootstrap/r2-bootstrap.json',
    [string]$ImportCode = '',
    [string]$ManifestPath = '',
    [string]$AccountId = '',
    [string]$Bucket = '',
    [string]$ManifestObjectKey = '',
    [string]$ConfigObjectKey = '',
    [string]$RuntimeEnvObjectKey = '',
    [string]$AccessKeyId = '',
    [string]$SecretAccessKey = '',
    [string]$Endpoint = '',
    [string]$ExpectedConfigSha256 = '',
    [string]$ExpectedRuntimeEnvSha256 = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'lib/easybrowser-config.ps1')

$importSyncEnabled = $null
$importSyncIntervalSeconds = $null

if (-not [string]::IsNullOrWhiteSpace($ImportCode)) {
    $importPayloadPath = New-EasyBrowserTempFile -Prefix 'easybrowser-import-code' -Extension '.json'
    try {
        Assert-EasyBrowserPythonModule -ModuleName 'nacl' -PackageName 'pynacl'
        & python (Join-Path $PSScriptRoot 'easybrowser-import-code.py') inspect `
            --import-code $ImportCode `
            --output $importPayloadPath
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to decode import code with exit code $LASTEXITCODE"
        }

        $importPayload = Get-Content -LiteralPath $importPayloadPath -Raw | ConvertFrom-Json
        if (-not $AccountId) { $AccountId = [string]$importPayload.accountId }
        if (-not $Bucket) { $Bucket = [string]$importPayload.bucket }
        if (-not $Endpoint) { $Endpoint = [string]$importPayload.endpoint }
        if (-not $ManifestObjectKey) { $ManifestObjectKey = [string]$importPayload.manifestObjectKey }
        if (-not $AccessKeyId) { $AccessKeyId = [string]$importPayload.accessKeyId }
        if (-not $SecretAccessKey) { $SecretAccessKey = [string]$importPayload.secretAccessKey }
        $importSyncEnabled = $importPayload.syncEnabled
        $importSyncIntervalSeconds = $importPayload.syncIntervalSeconds
    } finally {
        Remove-Item -LiteralPath $importPayloadPath -ErrorAction SilentlyContinue
    }
}

if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
    $resolvedManifestPath = Resolve-EasyBrowserPath -Path $ManifestPath
    if (-not (Test-Path -LiteralPath $resolvedManifestPath)) {
        throw "ManifestPath not found: $resolvedManifestPath"
    }

    $manifest = Get-Content -LiteralPath $resolvedManifestPath -Raw | ConvertFrom-Json
    if (-not $AccountId) { $AccountId = [string]$manifest.accountId }
    if (-not $Bucket) { $Bucket = [string]$manifest.bucket }
    if (-not $Endpoint) { $Endpoint = [string]$manifest.endpoint }
    if (-not $ManifestObjectKey) { $ManifestObjectKey = [string]$manifest.manifestObjectKey }
    if (-not $ConfigObjectKey) { $ConfigObjectKey = [string]$manifest.serviceBase.config.objectKey }
    if (-not $RuntimeEnvObjectKey) { $RuntimeEnvObjectKey = [string]$manifest.serviceBase.runtimeEnv.objectKey }
    if (-not $ExpectedConfigSha256) { $ExpectedConfigSha256 = [string]$manifest.serviceBase.config.sha256 }
    if (-not $ExpectedRuntimeEnvSha256) { $ExpectedRuntimeEnvSha256 = [string]$manifest.serviceBase.runtimeEnv.sha256 }
}

foreach ($required in @(
    @{ Name = 'AccountId'; Value = $AccountId },
    @{ Name = 'Bucket'; Value = $Bucket },
    @{ Name = 'ManifestObjectKey or ConfigObjectKey'; Value = if ([string]::IsNullOrWhiteSpace($ManifestObjectKey)) { $ConfigObjectKey } else { $ManifestObjectKey } },
    @{ Name = 'AccessKeyId'; Value = $AccessKeyId },
    @{ Name = 'SecretAccessKey'; Value = $SecretAccessKey }
)) {
    if ([string]::IsNullOrWhiteSpace([string]$required.Value)) {
        throw "$($required.Name) is required."
    }
}

$bootstrap = [ordered]@{
    accountId = $AccountId
    endpoint = if ([string]::IsNullOrWhiteSpace($Endpoint)) {
        "https://$AccountId.r2.cloudflarestorage.com"
    } else {
        $Endpoint
    }
    bucket = $Bucket
    accessKeyId = $AccessKeyId
    secretAccessKey = $SecretAccessKey
}

if (-not [string]::IsNullOrWhiteSpace($ManifestObjectKey)) {
    $bootstrap.manifestObjectKey = $ManifestObjectKey
}
if (-not [string]::IsNullOrWhiteSpace($ConfigObjectKey)) {
    $bootstrap.configObjectKey = $ConfigObjectKey
}
if (-not [string]::IsNullOrWhiteSpace($RuntimeEnvObjectKey)) {
    $bootstrap.runtimeEnvObjectKey = $RuntimeEnvObjectKey
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedConfigSha256)) {
    $bootstrap.expectedConfigSha256 = $ExpectedConfigSha256
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedRuntimeEnvSha256)) {
    $bootstrap.expectedRuntimeEnvSha256 = $ExpectedRuntimeEnvSha256
}
if ($null -ne $importSyncEnabled) {
    $bootstrap.syncEnabled = [bool]$importSyncEnabled
}
if ($null -ne $importSyncIntervalSeconds -and [int]$importSyncIntervalSeconds -gt 0) {
    $bootstrap.syncIntervalSeconds = [int]$importSyncIntervalSeconds
}

$resolvedOutputPath = Resolve-EasyBrowserPath -Path $OutputPath
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedOutputPath) | Out-Null
$bootstrap | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $resolvedOutputPath -Encoding UTF8
Write-Host "Bootstrap file written: $resolvedOutputPath"
