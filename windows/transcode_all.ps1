# H.264 Transcode-All Driver Script
# =================================
# Runs the AVI, MOV, and MP4 H.264 transcode scripts in order.
#
# USAGE:
#   .\transcode_all.ps1           # Process current directory only
#   .\transcode_all.ps1 -Recurse  # Process recursively from current directory
#
# The recursive flag is cascaded to each child script.

param(
    [switch]$Recurse
)

$ErrorActionPreference = "Continue"
$failedCount = 0
# Resolve the driver location so child scripts are loaded next to this file,
# even when the driver is invoked from another working directory.
$scriptPath = if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) {
    $PSCommandPath
}
elseif ($MyInvocation.MyCommand.Path) {
    $MyInvocation.MyCommand.Path
}
else {
    throw "Unable to determine transcode_all.ps1 script path."
}
$resolvedScriptPath = (Resolve-Path -LiteralPath $scriptPath).ProviderPath
$scriptDir = Split-Path -Parent $resolvedScriptPath
$powerShellCommand = if (Get-Command pwsh -ErrorAction SilentlyContinue) {
    "pwsh"
}
elseif (Get-Command powershell.exe -ErrorAction SilentlyContinue) {
    "powershell.exe"
}
else {
    "powershell"
}

$childArgs = @()
if ($Recurse) {
    $childArgs += "-Recurse"
}

function Invoke-ChildTranscodeScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptName
    )

    $scriptPath = Join-Path $scriptDir $ScriptName

    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        Write-Error "Required child script not found: $scriptPath"
        $script:failedCount++
        return
    }

    Write-Host ""
    Write-Host "=== Running $ScriptName ==="

    $processArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath) + $childArgs
    & $powerShellCommand @processArgs
    $status = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }

    if ($status -eq 0) {
        Write-Host "=== Completed $ScriptName successfully ==="
    }
    else {
        Write-Error "$ScriptName exited with status $status. Continuing with remaining scripts."
        $script:failedCount++
    }
}

Invoke-ChildTranscodeScript -ScriptName "h264-avi-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-mov-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-transcode.ps1"

if ($failedCount -gt 0) {
    exit 1
}

exit 0
