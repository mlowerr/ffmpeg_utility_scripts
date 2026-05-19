param([switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads)
$hw = "software"
if ($UseQuickSync) { $hw = "qsv" } elseif ($UseNVENC) { $hw = "nvenc" } elseif ($UseAMF) { $hw = "amf" }
$args = @("--profile", "wav_mp3", "--hw", $hw)
if ($Recurse) { $args += "--recursive" }
if ($PSBoundParameters.ContainsKey("Threads")) { $args += @("--threads", $Threads) }
& python3 (Join-Path $PSScriptRoot "..\cross-platform\transcode_cli.py") @args
exit $LASTEXITCODE
