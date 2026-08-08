param([Alias("c")][switch]$CudaDecode,[switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads,[string[]]$SkipDir,[int]$Quality,[string]$ConfigPath,[switch]$Resume,[double]$SegmentDuration)
$generic = Join-Path $PSScriptRoot "..\..\cross-platform\transcode-cli.ps1"
& $generic -Profile "h264_wmv" @PSBoundParameters
exit $LASTEXITCODE