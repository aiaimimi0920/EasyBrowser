$ErrorActionPreference = 'Stop'
$startScript = Resolve-Path (Join-Path $PSScriptRoot '..\deploy\service\base\scripts\start-easybrowser.ps1')
$serviceBinary = Resolve-Path (Join-Path $PSScriptRoot '..\service\base') -ErrorAction Stop
$serviceBinaryPath = Join-Path $serviceBinary 'easybrowser.exe'
$hadExistingBinary = Test-Path -LiteralPath $serviceBinaryPath
$proc = Start-Process -FilePath 'powershell' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $startScript) -PassThru -WindowStyle Hidden

try {
  Start-Sleep -Seconds 3
  $health = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/healthz'
  if (-not $health.success -or $health.data.status -ne 'ok') {
    throw "Unexpected /healthz response: $($health | ConvertTo-Json -Depth 8)"
  }
  Write-Host '[test-service-base-instance] /healthz ok'
}
finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
  Get-Process easybrowser -ErrorAction SilentlyContinue | Stop-Process -Force
  if (-not $hadExistingBinary -and (Test-Path -LiteralPath $serviceBinaryPath)) {
    Remove-Item -LiteralPath $serviceBinaryPath -Force
  }
}
