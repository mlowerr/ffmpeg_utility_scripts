# HEVC/H.265 MKV Transcoding Script
# =================================
# This script transcodes MKV video files to HEVC/H.265 format using ffmpeg.
# It targets smaller file sizes while keeping quality comparable to the source.

param(
    [switch]$Recurse,
    [switch]$UseQuickSync,
    [switch]$UseNVENC,
    [switch]$UseAMF,
    [ValidateRange(0, 2147483647)]
    [int]$Threads = 0
)

$ErrorActionPreference = "Continue"

$videoCodec = "libx265"
$preset = "medium"
$qualityOpts = @("-crf", "24")

if ($UseQuickSync) {
    $videoCodec = "hevc_qsv"
    $preset = "medium"
    $qualityOpts = @("-global_quality", "24")
}
elseif ($UseNVENC) {
    $videoCodec = "hevc_nvenc"
    $preset = "p4"
    $qualityOpts = @("-rc", "vbr", "-cq", "24")
}
elseif ($UseAMF) {
    $videoCodec = "hevc_amf"
    $preset = "speed"
    $qualityOpts = @("-qp_i", "24", "-qp_p", "24", "-qp_b", "24")
}

$threadOpts = @()
$x265Opts = @()
if ($Threads -gt 0) {
    $threadOpts = @("-threads", "$Threads")
    if ($videoCodec -eq "libx265") {
        $x265Opts = @("-x265-params", "pools=$Threads")
    }
}

$tempOutput = $null
$recurseOption = if ($Recurse) { @{ Recurse = $true } } else { @{} }

function Test-ValidFilePath {
    param([string]$Path)
    if ($Path -match '[\x00-\x1f]') {
        Write-Warning "Skipping file with control characters in name: $Path"
        return $false
    }
    return $true
}

try {
    Get-ChildItem -File @recurseOption | Where-Object { $_.Name -like "* *" } | ForEach-Object {
        $oldName = $_.Name
        $newName = $oldName -replace ' ', '_'
        if ($oldName -ne $newName) {
            $targetPath = Join-Path $_.DirectoryName $newName
            if (Test-Path -LiteralPath $targetPath) {
                Write-Host "Skipping rename: '$oldName' -> '$newName' (target already exists)"
            }
            else {
                Rename-Item -LiteralPath $_.FullName -NewName $newName -Verbose
            }
        }
    }

    $filesToProcess = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    Get-ChildItem -File @recurseOption | Where-Object {
        $_.Extension -ieq ".mkv" -and $_.Name -notlike "*_HEVC.mkv"
    } | ForEach-Object {
        if (-not (Test-ValidFilePath -Path $_.FullName)) {
            return
        }
        $output = Join-Path $_.DirectoryName ([System.IO.Path]::GetFileNameWithoutExtension($_.Name) + "_HEVC.mkv")
        if (-not (Test-Path -LiteralPath $output)) {
            $filesToProcess.Add($_)
        }
    }

    $totalFiles = $filesToProcess.Count
    if ($totalFiles -eq 0) {
        Write-Host "No eligible MKV files found to process."
        exit 0
    }

    $fileIndex = 0
    foreach ($file in $filesToProcess) {
        try {
            $fileIndex++
            $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
            $directory = $file.DirectoryName
            $output = Join-Path $directory ($baseName + "_HEVC.mkv")
            $tempOutput = Join-Path $directory ($baseName + "_HEVC.tmp.mkv")

            if (Test-Path -LiteralPath $tempOutput) {
                Remove-Item -LiteralPath $tempOutput -Force
            }

            Write-Host "`n`nProcessing file $fileIndex of $totalFiles`n`n"
            Write-Host "Transcoding '$($file.FullName)' using $videoCodec..."

            & ffmpeg -hide_banner -loglevel warning -stats `
                -i $file.FullName `
                -map 0:v:0? -map 0:a? -map 0:s? `
                -c:v $videoCodec `
                @x265Opts `
                @qualityOpts `
                -preset $preset `
                -c:a copy `
                -c:s copy `
                -map_metadata -1 `
                @threadOpts `
                -y `
                -- $tempOutput

            Write-Host "`n`n"

            if ($LASTEXITCODE -eq 0) {
                if ((Test-Path -LiteralPath $tempOutput) -and ((Get-Item -LiteralPath $tempOutput).Length -gt 0)) {
                    & ffprobe -v error $tempOutput *> $null
                    if ($LASTEXITCODE -eq 0) {
                        try {
                            Move-Item -LiteralPath $tempOutput -Destination $output -ErrorAction Stop
                            Remove-Item -LiteralPath $file.FullName -ErrorAction Stop
                            Write-Host "Successfully transcoded '$($file.FullName)' to '$output'. Source deleted."
                        }
                        catch {
                            Write-Host "Error: Failed finalizing '$($file.FullName)'. Keeping source. $_"
                            if (Test-Path -LiteralPath $tempOutput) {
                                Remove-Item -LiteralPath $tempOutput -Force -ErrorAction SilentlyContinue
                            }
                        }
                    }
                    else {
                        Write-Host "Error: Output file verification failed for '$($file.FullName)'. Keeping source."
                        Remove-Item -LiteralPath $tempOutput -Force -ErrorAction SilentlyContinue
                    }
                }
                else {
                    Write-Host "Error: Temporary output '$([System.IO.Path]::GetFileName($tempOutput))' is empty. Keeping source '$($file.Name)'."
                    if (Test-Path -LiteralPath $tempOutput) {
                        Remove-Item -LiteralPath $tempOutput -Force
                    }
                }
            }
            else {
                Write-Host "Error: ffmpeg failed on '$($file.Name)'. Keeping source."
                if (Test-Path -LiteralPath $tempOutput) {
                    Remove-Item -LiteralPath $tempOutput -Force
                }
            }

            $tempOutput = $null
        }
        catch {
            Write-Warning "Unexpected error processing '$($file.FullName)': $_"
            if ($tempOutput -and (Test-Path -LiteralPath $tempOutput)) {
                Remove-Item -LiteralPath $tempOutput -Force -ErrorAction SilentlyContinue
            }
            $tempOutput = $null
            continue
        }
    }
}
finally {
    if ($tempOutput -and (Test-Path -LiteralPath $tempOutput)) {
        Remove-Item -LiteralPath $tempOutput -Force
    }
}
