# Generic transcode_cli.py wrapper for Windows.
# Usage: transcode-cli.ps1 -Profile <profile> [-Recurse] [-UseQuickSync|-UseNVENC|-UseAMF] [-Threads n] [-Quality n] [-ConfigPath path] [-SkipDir path] [-CudaDecode] [-Resume] [-SegmentDuration seconds] [-Path directory]
# This script is the single parsing implementation behind every windows/video, windows/audio,
# and windows/mkv-shrink.ps1 wrapper.

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Profile,
    [Alias("c")]
    [switch]$CudaDecode,
    [Alias("r")]
    [switch]$Recurse,
    [Alias("q")]
    [switch]$UseQuickSync,
    [Alias("n")]
    [switch]$UseNVENC,
    [Alias("a")]
    [switch]$UseAMF,
    [Alias("t")]
    [int]$Threads,
    [string[]]$SkipDir,
    [int]$Quality,
    [string]$ConfigPath,
    [switch]$Resume,
    [double]$SegmentDuration,
    [string]$Path
)

$hw = "software"
if ($UseQuickSync) { $hw = "qsv" } elseif ($UseNVENC) { $hw = "nvenc" } elseif ($UseAMF) { $hw = "amf" }
$args = @("--profile", $Profile, "--hw", $hw)
if ($Recurse) { $args += "--recurse" }
if ($PSBoundParameters.ContainsKey("Threads")) { $args += @("--threads", $Threads) }
if ($PSBoundParameters.ContainsKey("Quality")) { $args += @("--quality", $Quality) }
if ($PSBoundParameters.ContainsKey("ConfigPath")) { $args += @("--config", $ConfigPath) }
if ($SkipDir) { foreach ($d in $SkipDir) { $args += @("--skip-dir", $d) } }
if ($PSBoundParameters.ContainsKey("Path")) { $args += @("--path", $Path) }
if ($CudaDecode) { $args += "--cuda-decode" }
if ($Resume) { $args += "--resume" }
if ($PSBoundParameters.ContainsKey("SegmentDuration")) { $args += @("--segment-duration", $SegmentDuration) }

$cliPath = Join-Path $PSScriptRoot "transcode_cli.py"
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $cliPath @args
}
elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 $cliPath @args
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $cliPath @args
}
else {
    Write-Error "Python launcher not found. Install Python and ensure py, python3, or python is on PATH."
    exit 1
}
exit $LASTEXITCODE