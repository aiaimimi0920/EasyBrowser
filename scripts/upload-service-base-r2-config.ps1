param(
    [string]$ConfigPath = 'config.yaml',
    [string]$AccountId = '',
    [string]$Bucket = '',
    [string]$AccessKeyId = '',
    [string]$SecretAccessKey = '',
    [string]$ConfigObjectKey = '',
    [string]$RuntimeEnvObjectKey = '',
    [string]$ManifestObjectKey = '',
    [string]$Endpoint = '',
    [string]$ReleaseVersion = '',
    [string]$ManifestOutput = '',
    [string]$ImageRef = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'lib/easybrowser-config.ps1')

foreach ($required in @(
    @{ Name = 'AccountId'; Value = $AccountId },
    @{ Name = 'Bucket'; Value = $Bucket },
    @{ Name = 'AccessKeyId'; Value = $AccessKeyId },
    @{ Name = 'SecretAccessKey'; Value = $SecretAccessKey },
    @{ Name = 'ConfigObjectKey'; Value = $ConfigObjectKey },
    @{ Name = 'RuntimeEnvObjectKey'; Value = $RuntimeEnvObjectKey },
    @{ Name = 'ManifestObjectKey'; Value = $ManifestObjectKey }
)) {
    if ([string]::IsNullOrWhiteSpace([string]$required.Value)) {
        throw "$($required.Name) is required."
    }
}

$resolvedConfigPath = Resolve-EasyBrowserPath -Path $ConfigPath
$renderConfigOutput = New-EasyBrowserTempFile -Prefix 'service-base-runtime-config' -Extension '.yaml'
$renderEnvOutput = New-EasyBrowserTempFile -Prefix 'service-base-runtime-env' -Extension '.env'

try {
    & (Join-Path $PSScriptRoot 'render-derived-configs.ps1') `
        -ConfigPath $resolvedConfigPath `
        -ServiceOutput $renderConfigOutput `
        -ServiceEnvOutput $renderEnvOutput

    $pythonScript = Join-Path $PSScriptRoot 'upload-service-base-r2-config.py'
    $pythonArgs = @(
        $pythonScript,
        '--account-id', $AccountId,
        '--bucket', $Bucket,
        '--access-key-id', $AccessKeyId,
        '--secret-access-key', $SecretAccessKey,
        '--config-path', $renderConfigOutput,
        '--config-object-key', $ConfigObjectKey,
        '--runtime-env-path', $renderEnvOutput,
        '--runtime-env-object-key', $RuntimeEnvObjectKey,
        '--manifest-object-key', $ManifestObjectKey
    )
    if (-not [string]::IsNullOrWhiteSpace($Endpoint)) {
        $pythonArgs += @('--endpoint', $Endpoint)
    }
    if (-not [string]::IsNullOrWhiteSpace($ReleaseVersion)) {
        $pythonArgs += @('--release-version', $ReleaseVersion)
    }
    if (-not [string]::IsNullOrWhiteSpace($ManifestOutput)) {
        $pythonArgs += @('--manifest-output', (Resolve-EasyBrowserPath -Path $ManifestOutput))
    }
    if (-not [string]::IsNullOrWhiteSpace($ImageRef)) {
        $pythonArgs += @('--image-ref', $ImageRef)
    }

    Assert-EasyBrowserPythonModule -ModuleName 'boto3' -PackageName 'boto3'
    Assert-EasyBrowserPythonModule -ModuleName 'yaml' -PackageName 'pyyaml'
    & python @pythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "R2 upload failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item -LiteralPath $renderConfigOutput -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $renderEnvOutput -ErrorAction SilentlyContinue
}
