$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pythonCheck = python -c "import importlib.util; import sys; sys.stdout.write('yes' if importlib.util.find_spec('camoufox') else 'no')" 2>$null
if ($pythonCheck -ne 'yes') {
  Write-Host 'Skipping Camoufox smoke test because python package camoufox is not installed.'
  exit 0
}

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

  function Invoke-CamoufoxTask {
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
        provider = 'camoufox'
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

  $versionTask = Invoke-CamoufoxTask -RequestId 'req-camoufox-smoke-version-001' -OperationPayload @{
    action = 'get_version'
  }

  $openTask = Invoke-CamoufoxTask -RequestId 'req-camoufox-smoke-open-001' -OperationPayload @{
    action        = 'open_resource'
    resource_kind = 'page'
    url           = 'https://example.com'
  }

  $targetId = $openTask.wait.response.data.result.resource.id

  $getTask = $null
  if ($targetId) {
    $getTask = Invoke-CamoufoxTask -RequestId 'req-camoufox-smoke-get-001' -OperationPayload @{
      action        = 'get_resource'
      resource_kind = 'page'
      resource_id   = $targetId
    }
  }

  $listTask = Invoke-CamoufoxTask -RequestId 'req-camoufox-smoke-list-001' -OperationPayload @{
    action        = 'list_resources'
    resource_kind = 'page'
  }

  $closeTask = $null
  if ($targetId) {
    $closeTask = Invoke-CamoufoxTask -RequestId 'req-camoufox-smoke-close-001' -OperationPayload @{
      action        = 'close_resource'
      resource_kind = 'page'
      resource_id   = $targetId
    }
  }

  [PSCustomObject]@{
    get_version        = $versionTask
    open_url           = $openTask
    get_resource       = $getTask
    list_pages         = $listTask
    close_target       = $closeTask
    providers_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/providers')
    runtimes_response  = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/runtimes')
  } | ConvertTo-Json -Depth 20
}
finally {
  if ($proc -and !$proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}
