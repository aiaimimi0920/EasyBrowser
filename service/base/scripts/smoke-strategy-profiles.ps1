$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (!(Test-Path '.\easybrowser.exe')) {
  go build -o .\easybrowser.exe .\cmd\easybrowser
}

$proc = Start-Process -FilePath .\easybrowser.exe -PassThru

try {
  Start-Sleep -Seconds 2

  function Wait-Task {
    param(
      [Parameter(Mandatory = $true)]
      [string]$TaskId,
      [int]$MaxSeconds = 25
    )

    $last = $null
    $observed = @()
    for ($i = 0; $i -lt $MaxSeconds; $i++) {
      Start-Sleep -Seconds 1
      $last = Invoke-RestMethod -Method Get -Uri ("http://127.0.0.1:18080/v1/tasks/{0}" -f $TaskId)
      $observed += $last.data.state
      if ($last.data.state -notin @('running', 'allocating', 'queued', 'routing', 'starting_runtime')) {
        break
      }
    }

    [pscustomobject]@{
      observed_states = $observed
      response        = $last
    }
  }

  function Invoke-StrategyTask {
    param(
      [Parameter(Mandatory = $true)]
      [string]$RequestId,
      [Parameter(Mandatory = $true)]
      [string]$StrategyProfile,
      [Parameter(Mandatory = $true)]
      [hashtable]$OperationPayload
    )

    $body = @"
{
  "request_id": "$RequestId",
  "mode": "strategy",
  "target": {
    "strategy_profile": "$StrategyProfile"
  },
  "operation": {
    "kind": "task",
    "payload": $(ConvertTo-Json $OperationPayload -Depth 12)
  },
  "isolation": {
    "require_separate_process": true,
    "runtime_reuse": "prefer_reuse"
  }
}
"@

    $execute = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/v1/execute' -ContentType 'application/json' -Body $body
    $wait = Wait-Task -TaskId $execute.data.task_id
    [pscustomobject]@{
      execute = $execute
      wait    = $wait
    }
  }

  $stealthTask = Invoke-StrategyTask -RequestId 'req-strategy-stealth-001' -StrategyProfile 'stealth-first' -OperationPayload @{
    action        = 'open_resource'
    resource_kind = 'page'
    url           = 'https://example.com'
  }

  Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/admin/providers/camoufox/disable' | Out-Null
  try {
    $fallbackTask = Invoke-StrategyTask -RequestId 'req-strategy-fallback-001' -StrategyProfile 'stealth-first' -OperationPayload @{
      action        = 'open_resource'
      resource_kind = 'page'
      url           = 'https://example.com'
    }
  }
  finally {
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/admin/providers/camoufox/enable' | Out-Null
  }

  $chromeTask = Invoke-StrategyTask -RequestId 'req-strategy-chrome-001' -StrategyProfile 'chrome-first' -OperationPayload @{
    action        = 'open_resource'
    resource_kind = 'page'
    url           = 'https://example.com'
  }

  [pscustomobject]@{
    stealth_first           = $stealthTask
    stealth_first_fallback  = $fallbackTask
    chrome_first            = $chromeTask
    provider_health_summary_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/providers/health-summary')
    route_history_response  = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/history?limit=10')
    fallback_history_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/fallbacks?limit=10')
    route_rejections_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/rejections')
    route_insights_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/insights')
    route_window_insights_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/insights/windows')
    route_windows_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/windows')
    operational_events_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/events/recent?limit=10')
    route_summary_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/routes/summary?history_limit=10&fallback_limit=10&rejection_limit=10&event_limit=10')
    providers_response      = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/providers')
    runtimes_response       = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/runtimes')
  } | ConvertTo-Json -Depth 20
}
finally {
  if ($proc -and !$proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}
