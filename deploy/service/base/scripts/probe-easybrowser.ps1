$ErrorActionPreference = 'Stop'
$deployRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

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
if (-not $env:EASYBROWSER_BASE_URL -and -not $env:EASYBROWSER_LISTEN) {
  Import-DotEnv (Join-Path $deployRoot '.env.example')
}

if ($env:EASYBROWSER_BASE_URL) {
  $baseUrl = $env:EASYBROWSER_BASE_URL.TrimEnd('/')
} else {
  $listen = if ($env:EASYBROWSER_LISTEN) { $env:EASYBROWSER_LISTEN } else { '127.0.0.1:18080' }
  $baseUrl = "http://$listen"
}

foreach ($path in '/healthz', '/admin/providers', '/admin/runtimes') {
  $uri = "$baseUrl$path"
  Write-Host "[probe-easybrowser] GET $uri"
  $payload = Invoke-RestMethod -Method Get -Uri $uri
  $payload | ConvertTo-Json -Depth 12
}
