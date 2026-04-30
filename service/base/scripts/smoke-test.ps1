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
      [int]$MaxSeconds = 20
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

  $executeBody = @{
    request_id = 'req-smoke-001'
    mode = 'strategy'
    operation = @{
      kind = 'task'
      payload = @{
        action = 'open_resource'
        resource_kind = 'page'
        url = 'https://example.com'
      }
    }
    isolation = @{
      require_separate_process = $true
      runtime_reuse = 'prefer_reuse'
    }
  } | ConvertTo-Json -Depth 8

  $executeResp = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/v1/execute' -ContentType 'application/json' -Body $executeBody
  $taskId = $executeResp.data.task_id
  $wait = Wait-Task -TaskId $taskId

  [PSCustomObject]@{
    execute_response = $executeResp
    wait = $wait
    providers_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/providers')
    runtimes_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/runtimes')
  } | ConvertTo-Json -Depth 12
}
finally {
  if ($proc -and !$proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}
