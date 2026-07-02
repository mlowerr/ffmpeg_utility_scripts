param([Alias("c")][switch]$CudaDecode,[switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads,[string[]]$SkipDir,[int]$Quality,[string]$ConfigPath)
$hw = "software"
if ($UseQuickSync) { $hw = "qsv" } elseif ($UseNVENC) { $hw = "nvenc" } elseif ($UseAMF) { $hw = "amf" }
$args = @("--profile", "h264_avi", "--hw", $hw)
if ($Recurse) { $args += "--recurse" }
if ($PSBoundParameters.ContainsKey("Threads")) { $args += @("--threads", $Threads) }
if ($PSBoundParameters.ContainsKey("Quality")) { $args += @("--quality", $Quality) }
if ($PSBoundParameters.ContainsKey("ConfigPath")) { $args += @("--config", $ConfigPath) }
if ($SkipDir) { foreach ($d in $SkipDir) { $args += @("--skip-dir", $d) } }
if ($CudaDecode) { $args += "--cuda-decode" }
$cliPath = Join-Path $PSScriptRoot "..\..\cross-platform\transcode_cli.py"
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
