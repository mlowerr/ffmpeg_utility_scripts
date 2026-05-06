# FLAC to 256k MP3 Conversion Script
# ======================================
# Converts .flac audio files in the current directory (or recursively with -Recurse)
# to 256 kbps MP3 files using ffmpeg/libmp3lame.

param(
    [switch]$Recurse
)

$ErrorActionPreference = "Continue"
$failedCount = 0
$tempOutput = $null

function Rename-FilesWithSpaces {
    param([System.IO.DirectoryInfo]$Directory)

    Get-ChildItem -LiteralPath $Directory.FullName -File -Filter "*.flac" | Where-Object { $_.Name -like "* *" } | ForEach-Object {
        $newName = $_.Name -replace ' ', '_'
        $newPath = Join-Path $_.DirectoryName $newName
        if (Test-Path -LiteralPath $newPath) {
            Write-Warning "Skipping rename '$($_.FullName)' -> '$newPath' (target exists)"
            return
        }
        try {
            Rename-Item -LiteralPath $_.FullName -NewName $newName -ErrorAction Stop
            Write-Host "Renamed: '$($_.FullName)' -> '$newPath'"
        }
        catch {
            Write-Warning "Failed to rename '$($_.FullName)' -> '$newPath': $_"
        }
    }
}

function Get-AudioStreamCount {
    param([string]$Path)

    $streams = & ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 -- $Path 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $streams) {
        return 0
    }
    return @($streams | Where-Object { $_ -and $_.Trim().Length -gt 0 }).Count
}

function Convert-AudioFile {
    param(
        [System.IO.FileInfo]$File,
        [int]$Current,
        [int]$Total
    )

    if ($File.FullName.Contains("`n")) {
        Write-Warning "Skipping file with newline in name: '$($File.FullName)'"
        return
    }

    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($File.Name)
    $output = Join-Path $File.DirectoryName ($baseName + ".mp3")
    $script:tempOutput = Join-Path $File.DirectoryName ($baseName + ".tmp.mp3")

    if (Test-Path -LiteralPath $script:tempOutput) {
        Remove-Item -LiteralPath $script:tempOutput -Force
    }

    Write-Host "`n`nProcessing file $Current of $Total`n"
    Write-Host "Converting '$($File.FullName)' to 256k MP3..."

    & ffmpeg -hide_banner -loglevel warning -stats `
        -i $File.FullName `
        -vn `
        -map "0:a:0?" `
        -c:a libmp3lame `
        -b:a 256k `
        -map_metadata 0 `
        -id3v2_version 3 `
        -y `
        $script:tempOutput

    Write-Host "`n`n"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: ffmpeg failed on '$($File.FullName)'. Keeping source."
        if (Test-Path -LiteralPath $script:tempOutput) { Remove-Item -LiteralPath $script:tempOutput -Force }
        $script:failedCount++
        $script:tempOutput = $null
        return
    }

    if (-not (Test-Path -LiteralPath $script:tempOutput) -or ((Get-Item -LiteralPath $script:tempOutput).Length -le 0)) {
        Write-Host "Error: Temporary output '$script:tempOutput' is empty. Keeping source."
        if (Test-Path -LiteralPath $script:tempOutput) { Remove-Item -LiteralPath $script:tempOutput -Force }
        $script:failedCount++
        $script:tempOutput = $null
        return
    }

    $null = & ffprobe -v error -- $script:tempOutput 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Output verification failed for '$($File.FullName)'. Keeping source."
        Remove-Item -LiteralPath $script:tempOutput -Force -ErrorAction SilentlyContinue
        $script:failedCount++
        $script:tempOutput = $null
        return
    }

    $inputAudioStreams = Get-AudioStreamCount -Path $File.FullName
    $outputAudioStreams = Get-AudioStreamCount -Path $script:tempOutput
    if (($inputAudioStreams -gt 0) -and ($outputAudioStreams -lt 1)) {
        Write-Host "Error: No audio stream found in output for '$($File.FullName)'. Keeping source."
        Remove-Item -LiteralPath $script:tempOutput -Force -ErrorAction SilentlyContinue
        $script:failedCount++
        $script:tempOutput = $null
        return
    }

    try {
        Move-Item -LiteralPath $script:tempOutput -Destination $output -ErrorAction Stop
        Remove-Item -LiteralPath $File.FullName -ErrorAction Stop
        Write-Host "Successfully converted '$($File.FullName)' to '$output'. Source deleted."
    }
    catch {
        Write-Host "Error: Failed finalizing '$($File.FullName)'. Keeping source. $_"
        if (Test-Path -LiteralPath $script:tempOutput) { Remove-Item -LiteralPath $script:tempOutput -Force -ErrorAction SilentlyContinue }
        $script:failedCount++
    }

    $script:tempOutput = $null
}

try {
    Rename-FilesWithSpaces -Directory (Get-Item -LiteralPath (Get-Location).Path)
    if ($Recurse) {
        Get-ChildItem -LiteralPath (Get-Location).Path -Directory -Recurse | ForEach-Object {
            Rename-FilesWithSpaces -Directory $_
        }
    }

    $fileParams = @{ LiteralPath = (Get-Location).Path; File = $true; Filter = "*.flac" }
    if ($Recurse) { $fileParams.Recurse = $true }
    $filesToProcess = New-Object System.Collections.Generic.List[System.IO.FileInfo]

    Get-ChildItem @fileParams | ForEach-Object {
        $output = Join-Path $_.DirectoryName ([System.IO.Path]::GetFileNameWithoutExtension($_.Name) + ".mp3")
        if (-not (Test-Path -LiteralPath $output)) {
            $filesToProcess.Add($_)
        }
    }

    if ($filesToProcess.Count -eq 0) {
        Write-Host "No eligible FLAC files found to process."
        exit 0
    }

    $fileIndex = 0
    foreach ($file in $filesToProcess) {
        $fileIndex++
        Convert-AudioFile -File $file -Current $fileIndex -Total $filesToProcess.Count
    }
}
finally {
    if ($tempOutput -and (Test-Path -LiteralPath $tempOutput)) {
        Remove-Item -LiteralPath $tempOutput -Force -ErrorAction SilentlyContinue
    }
}

if ($failedCount -gt 0) { exit 1 }
exit 0
