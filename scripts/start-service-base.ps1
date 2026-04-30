$ErrorActionPreference = 'Stop'
$script = Resolve-Path (Join-Path $PSScriptRoot '..\deploy\service\base\scripts\start-easybrowser.ps1')
& $script @args
