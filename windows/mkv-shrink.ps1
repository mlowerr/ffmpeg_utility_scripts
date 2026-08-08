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
$generic = Join-Path $PSScriptRoot "..\cross-platform\transcode-cli.ps1"
$fw = @{}
foreach ($k in $PSBoundParameters.Keys) { $fw[$k] = $PSBoundParameters[$k] }
if (-not $fw.ContainsKey("Threads")) { $fw["Threads"] = 8 }
if (-not $fw.ContainsKey("Path")) { $fw["Path"] = "." }
if (-not (Test-Path -LiteralPath $generic -PathType Leaf)) {
    Write-Error "Shared transcode launcher not found: $generic"
    exit 1
}
try {
    & $generic -Profile "mkv_shrink" @fw
    $invocationSucceeded = $?
    $status = $LASTEXITCODE
}
catch {
    Write-Error "Failed to invoke shared transcode launcher: $_"
    exit 1
}
if (-not $invocationSucceeded -or $null -eq $status) { exit 1 }
exit $status