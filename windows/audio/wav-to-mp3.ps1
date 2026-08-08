param([switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads,[string[]]$SkipDir,[int]$Quality,[string]$ConfigPath)
$generic = Join-Path $PSScriptRoot "..\..\cross-platform\transcode-cli.ps1"
& $generic -Profile "wav_mp3" @PSBoundParameters
exit $LASTEXITCODE