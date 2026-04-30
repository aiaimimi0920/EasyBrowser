$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$configExample = Join-Path $repoRoot 'config.example.yaml'
$configPath = Join-Path $repoRoot 'config.yaml'

if (Test-Path -LiteralPath $configPath) {
  Write-Host "[init-config] config.yaml already exists"
  exit 0
}

Copy-Item -LiteralPath $configExample -Destination $configPath
Write-Host "[init-config] created config.yaml from config.example.yaml"
