param(
  [string]$ImageName = 'easy-browser/easy-browser:local',
  [switch]$NoCache
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$dockerfile = Join-Path $repoRoot 'deploy\service\base\Dockerfile'

$args = @('build', '-f', $dockerfile, '-t', $ImageName)
if ($NoCache) {
  $args += '--no-cache'
}
$args += $repoRoot

Write-Host "[compile-service-base-image] docker $($args -join ' ')"
& docker @args
