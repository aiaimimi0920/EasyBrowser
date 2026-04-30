$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $env:BROWSERBASE_API_KEY) {
  Write-Host 'Skipping Browserbase smoke test because BROWSERBASE_API_KEY is not set.'
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

  function Redact-BrowserbasePayload {
    param(
      [Parameter(Mandatory = $true)]
      $InputObject
    )

    $json = $InputObject | ConvertTo-Json -Depth 20
    $copy = $json | ConvertFrom-Json

    $sensitiveKeys = @(
      'connectUrl',
      'signingKey',
      'seleniumRemoteUrl',
      'debuggerFullscreenUrl',
      'debuggerUrl',
      'downloadUrl'
    )

    function Visit([object]$Node) {
      if ($null -eq $Node) { return }
      if ($Node -is [System.Collections.IEnumerable] -and $Node -isnot [string]) {
        foreach ($item in $Node) { Visit $item }
        return
      }

      $props = $Node.PSObject.Properties
      if (-not $props) { return }
      foreach ($prop in $props) {
        if ($sensitiveKeys -contains $prop.Name) {
          $Node.$($prop.Name) = '[REDACTED]'
        } else {
          Visit $prop.Value
        }
      }
    }

    Visit $copy
    return $copy
  }

  function Invoke-EasyBrowserTask {
    param(
      [Parameter(Mandatory = $true)]
      [string]$RequestId,
      [Parameter(Mandatory = $true)]
      [hashtable]$OperationPayload
    )

    $executeBody = @{
      request_id = $RequestId
      mode       = 'specified'
      target     = @{
        provider = 'browserbase'
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

    $executeResp = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/v1/execute' -ContentType 'application/json' -Body $executeBody
    $taskId = $executeResp.data.task_id
    $wait = Wait-Task -TaskId $taskId

    [pscustomobject]@{
      execute = $executeResp
      wait    = $wait
    }
  }

  $listTask = Invoke-EasyBrowserTask -RequestId 'req-browserbase-smoke-list-001' -OperationPayload @{
    action        = 'list_resources'
    resource_kind = 'session'
  }

  $sessionId = $null
  $createTask = $null
  $getTask = $null
  $releaseTask = $null

  if ($env:BROWSERBASE_PROJECT_ID) {
    $createTask = Invoke-EasyBrowserTask -RequestId 'req-browserbase-smoke-create-001' -OperationPayload @{
      action         = 'open_resource'
      resource_kind  = 'session'
      project_id     = $env:BROWSERBASE_PROJECT_ID
      keep_alive     = $false
      user_metadata = @{
        source = 'easybrowser-smoke'
      }
    }

    $sessionId = $createTask.wait.response.data.result.resource.id

    if ($sessionId) {
      $getTask = Invoke-EasyBrowserTask -RequestId 'req-browserbase-smoke-get-001' -OperationPayload @{
        action        = 'get_resource'
        resource_kind = 'session'
        resource_id   = $sessionId
      }

      $releaseTask = Invoke-EasyBrowserTask -RequestId 'req-browserbase-smoke-release-001' -OperationPayload @{
        action        = 'close_resource'
        resource_kind = 'session'
        resource_id   = $sessionId
        project_id    = $env:BROWSERBASE_PROJECT_ID
      }
    }
  }

  [PSCustomObject]@{
    list_sessions     = (Redact-BrowserbasePayload -InputObject $listTask)
    create_session    = if ($createTask) { Redact-BrowserbasePayload -InputObject $createTask } else { $null }
    get_session       = if ($getTask) { Redact-BrowserbasePayload -InputObject $getTask } else { $null }
    request_release   = if ($releaseTask) { Redact-BrowserbasePayload -InputObject $releaseTask } else { $null }
    providers_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/providers')
    runtimes_response = (Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:18080/admin/runtimes')
  } | ConvertTo-Json -Depth 20
}
finally {
  if ($proc -and !$proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}
