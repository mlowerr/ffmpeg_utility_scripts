param(
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
    [int]$Threads = 8,
    [string[]]$SkipDir,
    [int]$Quality,
    [string]$ConfigPath,
    [switch]$Resume,
    [double]$SegmentDuration,
    [string]$Path = "."
)
$hw = "software"
if ($UseQuickSync) { $hw = "qsv" } elseif ($UseNVENC) { $hw = "nvenc" } elseif ($UseAMF) { $hw = "amf" }
$args = @("--profile", "mkv_shrink", "--path", $Path, "--threads", $Threads, "--hw", $hw)
if ($Recurse) { $args += "--recurse" }
if ($PSBoundParameters.ContainsKey("Quality")) { $args += @("--quality", $Quality) }
if ($PSBoundParameters.ContainsKey("ConfigPath")) { $args += @("--config", $ConfigPath) }
if ($SkipDir) { foreach ($d in $SkipDir) { $args += @("--skip-dir", $d) } }
if ($CudaDecode) { $args += "--cuda-decode" }
if ($Resume) { $args += "--resume" }
if ($PSBoundParameters.ContainsKey("SegmentDuration")) { $args += @("--segment-duration", $SegmentDuration) }
$cliPath = Join-Path $PSScriptRoot "..\cross-platform\transcode_cli.py"
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
