# Video Transcode-All Driver Script
# =================================
# Runs the AVI, FLV, MOV, MPG, MPEG, RM, RMVB, WMV, and MP4 H.264 transcode scripts,
# followed by the MKV HEVC transcode script.
#
# USAGE:
#   .\transcode_all_video.ps1           # Process current directory only
#   .\transcode_all_video.ps1 -Recurse  # Process recursively from current directory
#   .\transcode_all_video.ps1 -n        # Use NVIDIA NVENC in child scripts
#   .\transcode_all_video.ps1 -n -c     # Request CUDA decode with NVENC
#   .\transcode_all_video.ps1 -q -Quality 24 -SkipDir .\archive
#
# Supported child-wrapper options are cascaded to each child script.

param(
    [switch]$Recurse,
    [Alias("n")]
    [switch]$UseNVENC,
    [Alias("q")]
    [switch]$UseQuickSync,
    [Alias("a")]
    [switch]$UseAMF,
    [Alias("c")]
    [switch]$CudaDecode,
    [Alias("t")]
    [int]$Threads,
    [string[]]$SkipDir,
    [int]$Quality,
    [string]$ConfigPath,
    [switch]$Resume,
    [double]$SegmentDuration
)

$hardwareSelectionCount = @($UseQuickSync, $UseNVENC, $UseAMF).Where({ $_ }).Count
if ($hardwareSelectionCount -gt 1) {
    Write-Error "UseQuickSync, UseNVENC, and UseAMF are mutually exclusive. Select at most one hardware encoder."
    exit 1
}

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
    throw "Unable to determine transcode_all_video.ps1 script path."
}
$resolvedScriptPath = (Resolve-Path -LiteralPath $scriptPath).ProviderPath
$scriptDir = Split-Path -Parent $resolvedScriptPath
$powerShellCommand = Get-Command pwsh, powershell.exe, powershell -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $powerShellCommand) {
    Write-Error "No PowerShell executable found. Install PowerShell and ensure pwsh or powershell is on PATH."
    exit 1
}

$childArgs = @()
if ($Recurse) {
    $childArgs += "-Recurse"
}
if ($UseQuickSync) {
    $childArgs += "-UseQuickSync"
}
if ($UseNVENC) {
    $childArgs += "-UseNVENC"
}
if ($UseAMF) {
    $childArgs += "-UseAMF"
}
if ($PSBoundParameters.ContainsKey("Threads")) {
    $childArgs += @("-Threads", $Threads)
}
if ($PSBoundParameters.ContainsKey("Quality")) {
    $childArgs += @("-Quality", $Quality)
}
if ($PSBoundParameters.ContainsKey("ConfigPath")) {
    $childArgs += @("-ConfigPath", $ConfigPath)
}
if ($SkipDir) {
    $childArgs += "-SkipDir"
    $childArgs += $SkipDir
}
if ($CudaDecode) {
    $childArgs += "-CudaDecode"
}
if ($Resume) {
    $childArgs += "-Resume"
}
if ($PSBoundParameters.ContainsKey("SegmentDuration")) {
    $childArgs += @("-SegmentDuration", $SegmentDuration)
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
    try {
        & $powerShellCommand.Source @processArgs
        $invocationSucceeded = $?
        $status = $LASTEXITCODE
    }
    catch {
        Write-Error "Failed to launch ${ScriptName}: $_"
        $script:failedCount++
        return
    }
    if (-not $invocationSucceeded -or $null -eq $status) {
        Write-Error "Failed to launch ${ScriptName}: PowerShell did not return a process exit status."
        $script:failedCount++
        return
    }

    if ($status -eq 0) {
        Write-Host "=== Completed $ScriptName successfully ==="
    }
    else {
        Write-Warning "$ScriptName reported one or more file failures (status $status). See its failure summary above. Continuing with remaining scripts."
        $script:failedCount++
    }
}

Invoke-ChildTranscodeScript -ScriptName "h264-avi-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-flv-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-mov-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-m4v-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-mpg-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-mpeg-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-rm-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-rmvb-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-wmv-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "h264-transcode.ps1"
Invoke-ChildTranscodeScript -ScriptName "hevc-mkv-transcode.ps1"

if ($failedCount -gt 0) {
    exit 1
}

exit 0
