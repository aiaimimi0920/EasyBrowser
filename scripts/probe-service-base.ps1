$ErrorActionPreference = 'Stop'
$script = Resolve-Path (Join-Path $PSScriptRoot '..\deploy\service\base\scripts\probe-easybrowser.ps1')
& $script @args
