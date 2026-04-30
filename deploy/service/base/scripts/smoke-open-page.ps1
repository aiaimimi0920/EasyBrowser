param(
  [string]$Provider,
  [string]$Url
)

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
Import-DotEnv (Join-Path $deployRoot '.env.example')

if (!$Provider) { $Provider = $env:EASYBROWSER_SMOKE_PROVIDER }
if (!$Url) { $Url = if ($env:EASYBROWSER_SMOKE_URL) { $env:EASYBROWSER_SMOKE_URL } else { 'http://127.0.0.1:18888/recaptcha_v3.html' } }
$baseUrl = if ($env:EASYBROWSER_BASE_URL) { $env:EASYBROWSER_BASE_URL.TrimEnd('/') } else { "http://$($env:EASYBROWSER_LISTEN)" }

$target = @{}
if ($Provider) { $target.provider = $Provider }

$executeBody = @{
  request_id = "smoke-open-page-$([guid]::NewGuid())"
  mode = if ($Provider) { 'direct' } else { 'strategy' }
  target = $target
  operation = @{
    kind = 'open_page'
    payload = @{
      action = 'open_page'
      resource_kind = 'page'
      url = $Url
    }
  }
  isolation = @{
    require_separate_process = $true
    runtime_reuse = 'prefer_reuse'
  }
  metadata = @{
    caller = 'deploy-smoke'
    tags = @('lease', 'attach-contract')
  }
} | ConvertTo-Json -Depth 10

$submit = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/execute" -ContentType 'application/json' -Body $executeBody
$taskId = $submit.data.task_id
if (!$taskId) { throw "No task id returned: $($submit | ConvertTo-Json -Depth 12)" }

$status = $null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  $status = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$taskId"
  if ($status.data.state -notin @('queued','routing','allocating','starting_runtime','running')) { break }
}

$status | ConvertTo-Json -Depth 16

$result = $status.data.result
if ($result -and $result.resource_id) {
  $closeBody = @{
    request_id = "smoke-close-page-$([guid]::NewGuid())"
    mode = 'direct'
    target = @{
      provider = $status.data.route.selected_provider
      runtime_id = $status.data.route.runtime_id
    }
    operation = @{
      kind = 'close_resource'
      payload = @{
        action = 'close_resource'
        resource_kind = 'page'
        resource_id = $result.resource_id
      }
    }
    isolation = @{
      require_separate_process = $true
      runtime_reuse = 'require_reuse'
    }
  } | ConvertTo-Json -Depth 10

  $closeSubmit = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/execute" -ContentType 'application/json' -Body $closeBody
  Start-Sleep -Seconds 1
  Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$($closeSubmit.data.task_id)" | ConvertTo-Json -Depth 12
}
