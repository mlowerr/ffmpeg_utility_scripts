param([switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads,[string[]]$SkipDir,[int]$Quality,[string]$ConfigPath)
$generic = Join-Path $PSScriptRoot "..\..\cross-platform\transcode-cli.ps1"
if (-not (Test-Path -LiteralPath $generic -PathType Leaf)) {
    Write-Error "Shared transcode launcher not found: $generic"
    exit 1
}
try {
    & $generic -Profile "flac_mp3" @PSBoundParameters
    $invocationSucceeded = $?
    $status = $LASTEXITCODE
}
catch {
    Write-Error "Failed to invoke shared transcode launcher: $_"
    exit 1
}
if (-not $invocationSucceeded -or $null -eq $status) { exit 1 }
exit $status
