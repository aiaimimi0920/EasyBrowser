$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$serviceBase = Join-Path $repoRoot 'service\base'
$testServiceScript = Resolve-Path (Join-Path $PSScriptRoot 'test-service-base-instance.ps1')
$configPath = Join-Path $repoRoot 'config.yaml'
$createdConfig = $false

if (-not (Test-Path -LiteralPath $configPath)) {
  Copy-Item -LiteralPath (Join-Path $repoRoot 'config.example.yaml') -Destination $configPath
  $createdConfig = $true
}

try {
  Push-Location $serviceBase
  try {
    go test ./...
  }
  finally {
    Pop-Location
  }

  & $testServiceScript
}
finally {
  if ($createdConfig -and (Test-Path -LiteralPath $configPath)) {
    Remove-Item -LiteralPath $configPath -Force
  }
}
