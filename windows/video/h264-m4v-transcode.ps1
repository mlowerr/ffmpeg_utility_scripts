param([Alias("c")][switch]$CudaDecode,[switch]$Recurse,[switch]$UseQuickSync,[switch]$UseNVENC,[switch]$UseAMF,[int]$Threads,[string[]]$SkipDir,[int]$Quality,[string]$ConfigPath,[switch]$Resume,[double]$SegmentDuration)
$generic = Join-Path $PSScriptRoot "..\..\cross-platform\transcode-cli.ps1"
if (-not (Test-Path -LiteralPath $generic -PathType Leaf)) {
    Write-Error "Shared transcode launcher not found: $generic"
    exit 1
}
try {
    & $generic -Profile "h264_m4v" @PSBoundParameters
    $invocationSucceeded = $?
    $status = $LASTEXITCODE
}
catch {
    Write-Error "Failed to invoke shared transcode launcher: $_"
    exit 1
}
if (-not $invocationSucceeded -or $null -eq $status) { exit 1 }
exit $status
