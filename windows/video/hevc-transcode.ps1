param([Alias("c")][switch]$CudaDecode,[switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads,[string[]]$SkipDir,[int]$Quality,[string]$ConfigPath,[switch]$Resume,[double]$SegmentDuration)
$generic = Join-Path $PSScriptRoot "..\..\cross-platform\transcode-cli.ps1"
& $generic -Profile "hevc_mp4" @PSBoundParameters
exit $LASTEXITCODE