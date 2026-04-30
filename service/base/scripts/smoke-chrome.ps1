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

  function Invoke-ChromeTask {
    param(
      [Parameter(Mandatory = $true)]
      [string]$RequestId,
      [Parameter(Mandatory = $true)]
      [hashtable]$OperationPayload
    )

    $body = @{
      request_id = $RequestId
      mode       = 'specified'
      target     = @{
        provider = 'chrome'
      }
      operation  = @{
        kind    = 'task'
        payload = $OperationPayload
      }
      isolation  = @{
        require_separate_process = $true
        runtime_reuse            = 'prefer_reuse'
      }
    } | ConvertTo-Json -Depth 12

    $execute = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/v1/execute' -ContentType 'application/json' -Body $body
    $wait = Wait-Task -TaskId $execute.data.task_id
    [pscustomobject]@{
      execute = $execute
      wait    = $wait
    }
  }

  $openTask = Invoke-ChromeTask -RequestId 'req-chrome-smoke-open-001' -OperationPayload @{
    action        = 'open_resource'
    resource_kind = 'page'
    url           = 'https://example.com'
  }

  $targetId = $openTask.wait.response.data.result.resource.id

  $getTask = $null
  if ($targetId) {
    $getTask = Invoke-ChromeTask -RequestId 'req-chrome-smoke-get-001' -OperationPayload @{
      action        = 'get_resource'
      resource_kind = 'page'
      resource_id   = $targetId
    }
  }

  $listTask = Invoke-ChromeTask -RequestId 'req-chrome-smoke-list-001' -OperationPayload @{
    action        = 'list_resources'
    resource_kind = 'page'
  }

  $closeTask = $null
  if ($targetId) {
    $closeTask = Invoke-ChromeTask -RequestId 'req-chrome-smoke-close-001' -OperationPayload @{
      action        = 'close_resource'
      resource_kind = 'page'
      resource_id   = $targetId
    }
  }

  [pscustomobject]@{
    open_url          = $openTask
    get_resource      = $getTask
    list_pages        = $listTask
    close_target      = $closeTask
    providers_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/providers')
    runtimes_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/runtimes')
  } | ConvertTo-Json -Depth 20
}
finally {
  if ($proc -and !$proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}
