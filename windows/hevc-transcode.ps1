# HEVC/H.265 Video Transcoding Script
# ===================================
# This script transcodes MP4 video files to HEVC/H.265 format using ffmpeg.
# It significantly reduces file size while maintaining quality using CRF 24.
#
# WHAT IT DOES:
# - Renames files with spaces to use underscores
# - Transcodes .mp4 files to HEVC (libx265 codec, or hardware accel if requested)
# - Copies audio streams without re-encoding
# - Strips metadata to avoid stream mismatch errors
# - Deletes original files after successful transcoding
# - Skips files that have already been processed
#
# USAGE:
#   .\hevc-transcode.ps1              # Process current directory only (software)
#   .\hevc-transcode.ps1 -Recurse     # Process recursively from current directory
#   .\hevc-transcode.ps1 -Recurse -UseQuickSync   # Use Intel Quick Sync
#   .\hevc-transcode.ps1 -Recurse -UseNVENC       # Use NVIDIA NVENC
#   .\hevc-transcode.ps1 -Recurse -UseAMF         # Use AMD AMF
#
# OUTPUT:
# - Creates files with "_HEVC.mp4" suffix (e.g., "video_HEVC.mp4")
# - Temporary files use "_HEVC.tmp.mp4" during processing
#
# REQUIREMENTS:
# - ffmpeg must be installed and in your PATH
# - PowerShell 5.1 or later

param(
    [switch]$Recurse,
    [switch]$UseQuickSync,
    [switch]$UseNVENC,
    [switch]$UseAMF
)

$ErrorActionPreference = "Stop"

# Determine video codec and quality settings based on hardware acceleration option
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

$tempOutput = $null

# Determine recursion option for Get-ChildItem
$recurseOption = if ($Recurse) { @{ Recurse = $true } } else { @{} }

# Helper function to validate file path
function Test-ValidFilePath {
    param([string]$Path)
    # Check for control characters or other dangerous patterns
    if ($Path -match '[\x00-\x1f]') {
        Write-Warning "Skipping file with control characters in name: $Path"
        return $false
    }
    return $true
}

try {
    # 1. Rename files: replace literal spaces with underscores
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

    # 2. Collect eligible files in a single pass using List for efficiency
    $filesToProcess = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    Get-ChildItem -File @recurseOption | Where-Object { 
        $_.Extension -ieq ".mp4" -and $_.Name -notlike "*_HEVC.mp4" 
    } | ForEach-Object {
        if (-not (Test-ValidFilePath -Path $_.FullName)) {
            return
        }
        $output = Join-Path $_.DirectoryName ([System.IO.Path]::GetFileNameWithoutExtension($_.Name) + "_HEVC.mp4")
        if (-not (Test-Path -LiteralPath $output)) {
            $filesToProcess.Add($_)
        }
    }
    
    $totalFiles = $filesToProcess.Count
    
    if ($totalFiles -eq 0) {
        Write-Host "No eligible MP4 files found to process."
        exit 0
    }
    
    $fileIndex = 0
    
    # 3. Process collected files
    foreach ($file in $filesToProcess) {
        $fileIndex++
        
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
        $directory = $file.DirectoryName

        $output = Join-Path $directory ($baseName + "_HEVC.mp4")
        $tempOutput = Join-Path $directory ($baseName + "_HEVC.tmp.mp4")

        if (Test-Path -LiteralPath $tempOutput) {
            Remove-Item -LiteralPath $tempOutput -Force
        }

        # Print progress message with blank lines (batched for efficiency)
        Write-Host "`n`nProcessing file $fileIndex of $totalFiles`n`n"
        
        Write-Host "Transcoding '$($file.FullName)' using $videoCodec..."

        & ffmpeg -hide_banner -loglevel warning -stats `
            -i $file.FullName `
            -map 0:v:0? -map 0:a? `
            -c:v $videoCodec `
            @qualityOpts `
            -preset $preset `
            -c:a copy `
            -map_metadata -1 `
            -movflags +faststart `
            -y `
            -- $tempOutput

        # Print two blank lines after ffmpeg
        Write-Host "`n`n"

        if ($LASTEXITCODE -eq 0) {
            if ((Test-Path -LiteralPath $tempOutput) -and ((Get-Item -LiteralPath $tempOutput).Length -gt 0)) {
                # Verify output file integrity before deleting source
                $ffprobeTest = & ffprobe -v error $tempOutput 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Move-Item -LiteralPath $tempOutput -Destination $output
                    Remove-Item -LiteralPath $file.FullName
                    Write-Host "Successfully transcoded '$($file.FullName)' to '$output'. Source deleted."
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
}
finally {
    if ($tempOutput -and (Test-Path -LiteralPath $tempOutput)) {
        Remove-Item -LiteralPath $tempOutput -Force
    }
}
