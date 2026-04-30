Set-StrictMode -Version Latest

function Resolve-EasyBrowserPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'Path is required.'
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        if (Test-Path -LiteralPath $Path) {
            return (Resolve-Path -LiteralPath $Path).Path
        }
        return [System.IO.Path]::GetFullPath($Path)
    }

    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
    $candidate = Join-Path $repoRoot $Path
    if (Test-Path -LiteralPath $candidate) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    return [System.IO.Path]::GetFullPath($candidate)
}

function New-EasyBrowserTempFile {
    param(
        [string]$Prefix = 'easybrowser',
        [string]$Extension = '.tmp'
    )

    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
    $tmpDir = Join-Path $repoRoot '.tmp'
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

    $fileName = '{0}-{1}{2}' -f $Prefix, ([guid]::NewGuid().ToString('N')), $Extension
    return Join-Path $tmpDir $fileName
}

function Assert-EasyBrowserPythonModule {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ModuleName,
        [string]$PackageName = ''
    )

    $packageLabel = if ([string]::IsNullOrWhiteSpace($PackageName)) { $ModuleName } else { $PackageName }
    $script = @"
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("$ModuleName") else 1)
"@
    $script | python - | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Missing Python module '$ModuleName'. Install package '$packageLabel' first."
    }
}
