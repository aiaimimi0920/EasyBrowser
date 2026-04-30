$ErrorActionPreference = 'Stop'
$script = Resolve-Path (Join-Path $PSScriptRoot '..\deploy\service\base\scripts\smoke-open-page.ps1')
& $script @args
