#!/bin/bash
# HEVC/H.265 Video Transcoding Script
# ===================================
# This script transcodes MP4 video files to HEVC/H.265 format using ffmpeg.
# It significantly reduces file size while maintaining quality using CRF 26.
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
#   ./hevc-transcode.sh           # Process current directory only (software encoding)
#   ./hevc-transcode.sh -r        # Process recursively from current directory
#   ./hevc-transcode.sh -r -q     # Use Intel Quick Sync hardware acceleration
#   ./hevc-transcode.sh -r -n     # Use NVIDIA NVENC hardware acceleration
#   ./hevc-transcode.sh -r -a     # Use AMD AMF hardware acceleration
#
# OUTPUT:
# - Creates files with "_HEVC.mp4" suffix (e.g., "video_HEVC.mp4")
# - Temporary files use "_HEVC.tmp.mp4" during processing
#
# REQUIREMENTS:
# - ffmpeg must be installed and in your PATH
# - Bash 4.0 or later

set -u

# Parse arguments
RECURSE=false
USE_QSV=false
USE_NVENC=false
USE_AMF=false

while getopts "rqna" opt; do
    case $opt in
        r) RECURSE=true ;;
        q) USE_QSV=true ;;
        n) USE_NVENC=true ;;
        a) USE_AMF=true ;;
        *) echo "Usage: $0 [-r] [-q|-n|-a]"; exit 1 ;;
    esac
done

shopt -s nullglob nocaseglob

temp_output=""
trap 'rm -f -- "$temp_output"; exit' INT TERM EXIT

# Determine video codec and quality settings based on hardware acceleration option
VIDEO_CODEC="libx265"
PRESET="medium"
QUALITY_OPTS="-crf 26"

if [[ "$USE_QSV" == true ]]; then
    VIDEO_CODEC="hevc_qsv"
    PRESET="medium"
    QUALITY_OPTS="-global_quality 26"
elif [[ "$USE_NVENC" == true ]]; then
    VIDEO_CODEC="hevc_nvenc"
    PRESET="p4"
    QUALITY_OPTS="-rc vbr -cq 26"
elif [[ "$USE_AMF" == true ]]; then
    VIDEO_CODEC="hevc_amf"
    PRESET="speed"
    QUALITY_OPTS="-qp_i 26 -qp_p 26 -qp_b 26"
fi

# Sanitize filename for safe use in shell
sanitize_filename() {
    printf '%q' "$1"
}

# Function to rename files (replace spaces with underscores)
rename_files() {
    local dir="$1"
    for f in "$dir"/*" "*; do
        [[ -f "$f" ]] || continue

        local new_name
        new_name="${f// /_}"

        if [[ -e "$new_name" && "$f" != "$new_name" ]]; then
            echo "Skipping rename: '$f' -> '$new_name' (target already exists)"
            continue
        fi

        mv -v -- "$f" "$new_name"
    done
}

# Function to process a single file
# Arguments: $1 = file path, $2 = current index, $3 = total count
process_file() {
    local f="$1"
    local current="$2"
    local total="$3"
    local dir
    dir=$(dirname "$f")
    local base_name
    base_name=$(basename "$f" .mp4)

    local output="$dir/${base_name}_HEVC.mp4"
    local temp_out="$dir/${base_name}_HEVC.tmp.mp4"

    # Validate file path doesn't contain dangerous characters
    if [[ "$f" == *$'\n'* ]]; then
        echo "Warning: Skipping file with newline in name: $(sanitize_filename "$f")"
        return
    fi

    rm -f -- "$temp_out"
    temp_output="$temp_out"

    # Print progress message with blank lines
    printf '\n\nProcessing file %s of %s\n\n\n' "$current" "$total"
    
    printf 'Transcoding %q using %s...\n' "$f" "$VIDEO_CODEC"
    
    # shellcheck disable=SC2086
    if ffmpeg -hide_banner -loglevel warning -stats \
            -i "$f" \
            -map "0:v:0?" -map "0:a?" \
            -c:v "$VIDEO_CODEC" \
            $QUALITY_OPTS \
            -preset "$PRESET" \
            -c:a copy \
            -map_metadata -1 \
            -movflags +faststart \
            -y \
            -- "$temp_out"; then
        # Print two blank lines after ffmpeg
        printf '\n\n'
        
        if [[ -s "$temp_out" ]]; then
            # Verify output file integrity before deleting source
            if ffprobe -v error "$temp_out" >/dev/null 2>&1; then
                # Validate audio stream count wasn't dropped due to incompatible codec
                local input_audio_streams output_audio_streams
                input_audio_streams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$f" 2>/dev/null | wc -l)
                output_audio_streams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$temp_out" 2>/dev/null | wc -l)
                
                if [[ "$input_audio_streams" -gt 0 && "$output_audio_streams" -lt "$input_audio_streams" ]]; then
                    printf 'Error: Audio stream count mismatch for %q (%d input, %d output). Incompatible codec? Keeping source.\n' "$f" "$input_audio_streams" "$output_audio_streams"
                    rm -f -- "$temp_out"
                else
                    mv -- "$temp_out" "$output"
                    rm -- "$f"
                    printf 'Successfully transcoded %q to %q. Source deleted.\n' "$f" "$output"
                fi
            else
                printf 'Error: Output file verification failed for %q. Keeping source.\n' "$f"
                rm -f -- "$temp_out"
            fi
        else
            printf 'Error: Temporary output %q is empty. Keeping source %q.\n' "$temp_out" "$f"
            rm -f -- "$temp_out"
        fi
    else
        # Print two blank lines after ffmpeg
        printf '\n\n'
        printf 'Error: ffmpeg failed on %q. Keeping source.\n' "$f"
        rm -f -- "$temp_out"
    fi
    temp_output=""
}

# Main execution
if [[ "$RECURSE" == true ]]; then
    # Rename files recursively first
    while IFS= read -r -d '' dir; do
        rename_files "$dir"
    done < <(find . -type d -print0)

    # Collect eligible files in a single pass
    declare -a files_to_process
    while IFS= read -r -d '' f; do
        base_name=$(basename "$f")
        [[ "$base_name" == *_HEVC.mp4 ]] && continue
        output="${f%.*}_HEVC.mp4"
        [[ -e "$output" ]] && continue
        files_to_process+=("$f")
    done < <(find . -type f -iname "*.mp4" -print0)

    total_files=${#files_to_process[@]}
    
    if [[ $total_files -eq 0 ]]; then
        echo "No eligible MP4 files found to process."
        exit 0
    fi
    
    current_index=0

    # Process collected files
    for f in "${files_to_process[@]}"; do
        ((current_index++))
        process_file "$f" "$current_index" "$total_files"
    done
else
    # Non-recursive mode (current directory only)
    rename_files "."

    # Collect eligible files in a single pass
    declare -a files_to_process
    for f in *.mp4; do
        [[ -f "$f" ]] || continue
        [[ "$f" == *_HEVC.mp4 ]] && continue
        output="${f%.*}_HEVC.mp4"
        [[ -e "$output" ]] && continue
        files_to_process+=("$f")
    done

    total_files=${#files_to_process[@]}
    
    if [[ $total_files -eq 0 ]]; then
        echo "No eligible MP4 files found to process."
        exit 0
    fi
    
    current_index=0

    # Process collected files
    for f in "${files_to_process[@]}"; do
        ((current_index++))
        process_file "$f" "$current_index" "$total_files"
    done
fi
