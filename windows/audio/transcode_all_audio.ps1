# Audio Transcode-All Driver Script
# =================================
# Runs FLAC and WAV to MP3 conversion scripts in order.

param(
    [switch]$Recurse
)

$ErrorActionPreference = "Continue"
$failedCount = 0
$scriptPath = if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) {
    $PSCommandPath
}
elseif ($MyInvocation.MyCommand.Path) {
    $MyInvocation.MyCommand.Path
}
else {
    throw "Unable to determine transcode_all_audio.ps1 script path."
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

Invoke-ChildTranscodeScript -ScriptName "flac-to-mp3.ps1"
Invoke-ChildTranscodeScript -ScriptName "wav-to-mp3.ps1"

if ($failedCount -gt 0) {
    exit 1
}

exit 0
