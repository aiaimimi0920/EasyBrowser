param(
  [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$deployRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$repoRoot = Resolve-Path (Join-Path $deployRoot '..\..\..\service\base')

function Import-DotEnv([string]$Path) {
  if (!(Test-Path $Path)) { return }
  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if (!$line -or $line.StartsWith('#') -or $line.StartsWith(';')) { return }
    $idx = $line.IndexOf('=')
    if ($idx -lt 0) { return }
    $key = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path ("env:{0}" -f $key) -Value $value
  }
}

Import-DotEnv (Join-Path $deployRoot '.env')
Import-DotEnv (Join-Path $deployRoot '.env.local')
if (-not $env:EASYBROWSER_LISTEN) {
  Import-DotEnv (Join-Path $deployRoot '.env.example')
}

Push-Location $repoRoot
try {
  if ($Rebuild -or !(Test-Path '.\easybrowser.exe')) {
    go build -o .\easybrowser.exe .\cmd\easybrowser
  }

  Write-Host "[start-easybrowser] EASYBROWSER_LISTEN=$($env:EASYBROWSER_LISTEN)"
  & .\easybrowser.exe
}
finally {
  Pop-Location
}
