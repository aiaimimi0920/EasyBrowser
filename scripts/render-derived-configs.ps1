param(
    [string]$ConfigPath = 'config.yaml',
    [string]$ServiceOutput = '',
    [string]$ServiceEnvOutput = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'lib/easybrowser-config.ps1')

$resolvedConfigPath = Resolve-EasyBrowserPath -Path $ConfigPath
$resolvedServiceOutput = if ([string]::IsNullOrWhiteSpace($ServiceOutput)) { '' } else { Resolve-EasyBrowserPath -Path $ServiceOutput }
$resolvedServiceEnvOutput = if ([string]::IsNullOrWhiteSpace($ServiceEnvOutput)) {
    throw 'ServiceEnvOutput is required.'
} else {
    Resolve-EasyBrowserPath -Path $ServiceEnvOutput
}

Assert-EasyBrowserPythonModule -ModuleName 'yaml' -PackageName 'pyyaml'

$args = @(
    (Join-Path $PSScriptRoot 'render-derived-configs.py'),
    '--config', $resolvedConfigPath,
    '--service-env-output', $resolvedServiceEnvOutput
)
if (-not [string]::IsNullOrWhiteSpace($resolvedServiceOutput)) {
    $args += @('--service-output', $resolvedServiceOutput)
}

& python @args
if ($LASTEXITCODE -ne 0) {
    throw "Failed to render derived configs with exit code $LASTEXITCODE"
}
