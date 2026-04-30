param(
    [string]$OutputDirectory = '.runtime-keys'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'lib/easybrowser-config.ps1')

$resolvedOutputDirectory = Resolve-EasyBrowserPath -Path $OutputDirectory
New-Item -ItemType Directory -Force -Path $resolvedOutputDirectory | Out-Null

Assert-EasyBrowserPythonModule -ModuleName 'nacl' -PackageName 'pynacl'

$publicKeyPath = Join-Path $resolvedOutputDirectory 'easybrowser_import_code_owner_public.txt'
$privateKeyPath = Join-Path $resolvedOutputDirectory 'easybrowser_import_code_owner_private.txt'
$bundlePath = Join-Path $resolvedOutputDirectory 'easybrowser_import_code_owner_keypair.json'

& python (Join-Path $PSScriptRoot 'easybrowser-import-code.py') generate-keypair `
    --public-key-output $publicKeyPath `
    --private-key-output $privateKeyPath `
    --bundle-output $bundlePath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to generate import-code keypair with exit code $LASTEXITCODE"
}

Write-Host "Public key:  $publicKeyPath"
Write-Host "Private key: $privateKeyPath"
Write-Host "Bundle:      $bundlePath"
