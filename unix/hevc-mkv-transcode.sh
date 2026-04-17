#!/bin/bash
# HEVC/H.265 MKV Transcoding Script
# =================================
# This script transcodes MKV video files to HEVC/H.265 format using ffmpeg.
# It targets smaller file sizes while keeping quality comparable to the source.
#
# WHAT IT DOES:
# - Renames files with spaces to use underscores
# - Transcodes .mkv files to HEVC (libx265 codec, or hardware accel if requested)
# - Keeps primary video stream + all audio and subtitle streams
# - Excludes embedded artwork/attached picture streams by mapping only video stream 0
# - Strips container metadata to avoid stream mismatch issues
# - Deletes original files after successful transcoding
# - Skips files that have already been processed
#
# USAGE:
#   ./hevc-mkv-transcode.sh           # Process current directory only (software encoding)
#   ./hevc-mkv-transcode.sh -r        # Process recursively from current directory
#   ./hevc-mkv-transcode.sh -t 8      # Limit ffmpeg/x265 thread usage to 8 threads
#   ./hevc-mkv-transcode.sh -r -q     # Use Intel Quick Sync hardware acceleration
#   ./hevc-mkv-transcode.sh -r -n     # Use NVIDIA NVENC hardware acceleration
#   ./hevc-mkv-transcode.sh -r -a     # Use AMD AMF hardware acceleration
#
# OUTPUT:
# - Creates files with "_HEVC.mkv" suffix (e.g., "video_HEVC.mkv")
# - Temporary files use "_HEVC.tmp.mkv" during processing

set -u

FAILED_COUNT=0
RECURSE=false
USE_QSV=false
USE_NVENC=false
USE_AMF=false
THREADS=0

while getopts ":rqnat:" opt; do
    case $opt in
        r) RECURSE=true ;;
        q) USE_QSV=true ;;
        n) USE_NVENC=true ;;
        a) USE_AMF=true ;;
        t)
            if [[ "$OPTARG" =~ ^[1-9][0-9]*$ ]]; then
                THREADS="$OPTARG"
            else
                echo "Error: -t requires a positive integer (got '$OPTARG')." >&2
                echo "Usage: $0 [-r] [-q|-n|-a] [-t THREADS]"
                exit 1
            fi
            ;;
        :)
            echo "Error: Option -$OPTARG requires an argument." >&2
            echo "Usage: $0 [-r] [-q|-n|-a] [-t THREADS]"
            exit 1
            ;;
        \?)
            echo "Usage: $0 [-r] [-q|-n|-a] [-t THREADS]"
            exit 1
            ;;
    esac
done

shopt -s nullglob nocaseglob

temp_output=""
trap 'rm -f -- "$temp_output"; exit' INT TERM EXIT

VIDEO_CODEC="libx265"
PRESET="medium"
QUALITY_OPTS="-crf 24"

if [[ "$USE_QSV" == true ]]; then
    VIDEO_CODEC="hevc_qsv"
    PRESET="medium"
    QUALITY_OPTS="-global_quality 24"
elif [[ "$USE_NVENC" == true ]]; then
    VIDEO_CODEC="hevc_nvenc"
    PRESET="p4"
    QUALITY_OPTS="-rc vbr -cq 24"
elif [[ "$USE_AMF" == true ]]; then
    VIDEO_CODEC="hevc_amf"
    PRESET="speed"
    QUALITY_OPTS="-qp_i 24 -qp_p 24 -qp_b 24"
fi

THREAD_OPTS=()
X265_OPTS=()
if [[ "$THREADS" -gt 0 ]]; then
    THREAD_OPTS=(-threads "$THREADS")
    if [[ "$VIDEO_CODEC" == "libx265" ]]; then
        # libx265 manages its own worker pool; "pools" is the reliable knob.
        X265_OPTS=(-x265-params "pools=$THREADS")
    fi
fi

sanitize_filename() {
    printf '%q' "$1"
}

rename_files() {
    local dir="$1"
    for f in "$dir"/*" "*; do
        [[ -f "$f" ]] || continue
        local filename new_filename new_name
        filename=$(basename "$f")
        new_filename="${filename// /_}"
        new_name="$dir/$new_filename"
        [[ "$f" == "$new_name" ]] && continue
        if ! mv -n -v -- "$f" "$new_name" 2>/dev/null; then
            echo "Warning: Failed to rename '$f' -> '$new_name' (target exists or error)" >&2
            continue
        fi
    done
}

process_file() {
    local f="$1"
    local current="$2"
    local total="$3"
    local dir
    dir=$(dirname "$f")
    local base_name
    base_name=$(basename "$f")
    base_name="${base_name%.[Mm][Kk][Vv]}"

    local output="$dir/${base_name}_HEVC.mkv"
    local temp_out="$dir/${base_name}_HEVC.tmp.mkv"

    if [[ "$f" == *$'\n'* ]]; then
        echo "Warning: Skipping file with newline in name: $(sanitize_filename "$f")"
        return
    fi

    rm -f -- "$temp_out"
    temp_output="$temp_out"

    printf '\n\nProcessing file %s of %s\n\n\n' "$current" "$total"
    printf 'Transcoding %q using %s...\n' "$f" "$VIDEO_CODEC"

    # shellcheck disable=SC2086
    if ffmpeg -hide_banner -loglevel warning -stats \
            -i "$f" \
            -map "0:v:0?" -map "0:a?" -map "0:s?" \
            -c:v "$VIDEO_CODEC" \
            "${X265_OPTS[@]}" \
            $QUALITY_OPTS \
            -preset "$PRESET" \
            -c:a copy \
            -c:s copy \
            -map_metadata -1 \
            "${THREAD_OPTS[@]}" \
            -y \
            -- "$temp_out"; then
        printf '\n\n'

        if [[ -s "$temp_out" ]]; then
            if ffprobe -v error "$temp_out" >/dev/null 2>&1; then
                local input_audio_streams output_audio_streams
                input_audio_streams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$f" 2>/dev/null | wc -l)
                output_audio_streams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$temp_out" 2>/dev/null | wc -l)

                if [[ "$input_audio_streams" -gt 0 && "$output_audio_streams" -lt "$input_audio_streams" ]]; then
                    printf 'Error: Audio stream count mismatch for %q (%d input, %d output). Keeping source.\n' "$f" "$input_audio_streams" "$output_audio_streams" >&2
                    rm -f -- "$temp_out"
                    ((FAILED_COUNT++))
                else
                    if mv -- "$temp_out" "$output"; then
                        if rm -- "$f"; then
                            printf 'Successfully transcoded %q to %q. Source deleted.\n' "$f" "$output"
                        else
                            printf 'Warning: Transcoded %q but failed to remove source.\n' "$f" >&2
                            ((FAILED_COUNT++))
                        fi
                    else
                        printf 'Error: Failed to move temp file to output for %q.\n' "$f" >&2
                        rm -f -- "$temp_out"
                        ((FAILED_COUNT++))
                    fi
                fi
            else
                printf 'Error: Output file verification failed for %q. Keeping source.\n' "$f" >&2
                rm -f -- "$temp_out"
                ((FAILED_COUNT++))
            fi
        else
            printf 'Error: Temporary output %q is empty. Keeping source %q.\n' "$temp_out" "$f" >&2
            rm -f -- "$temp_out"
            ((FAILED_COUNT++))
        fi
    else
        printf '\n\n'
        printf 'Error: ffmpeg failed on %q. Keeping source.\n' "$f" >&2
        rm -f -- "$temp_out"
        ((FAILED_COUNT++))
    fi
    temp_output=""
}

if [[ "$RECURSE" == true ]]; then
    while IFS= read -r -d '' dir; do
        rename_files "$dir"
    done < <(find . -type d -print0)

    files_to_process=()
    while IFS= read -r -d '' f; do
        base_name=$(basename "$f")
        [[ "${base_name,,}" == *_hevc.mkv ]] && continue
        output="${f%.*}_HEVC.mkv"
        [[ -e "$output" ]] && continue
        files_to_process+=("$f")
    done < <(find . -type f -iname "*.mkv" -print0)

    total_files=${#files_to_process[@]}
    if [[ $total_files -eq 0 ]]; then
        echo "No eligible MKV files found to process."
        exit 0
    fi

    current_index=0
    for f in "${files_to_process[@]}"; do
        ((current_index++))
        process_file "$f" "$current_index" "$total_files"
    done
else
    rename_files "."

    files_to_process=()
    for f in *.mkv; do
        [[ -f "$f" ]] || continue
        [[ "${f,,}" == *_hevc.mkv ]] && continue
        output="${f%.*}_HEVC.mkv"
        [[ -e "$output" ]] && continue
        files_to_process+=("$f")
    done

    total_files=${#files_to_process[@]}
    if [[ $total_files -eq 0 ]]; then
        echo "No eligible MKV files found to process."
        exit 0
    fi

    current_index=0
    for f in "${files_to_process[@]}"; do
        ((current_index++))
        process_file "$f" "$current_index" "$total_files"
    done
fi

exit $(( FAILED_COUNT > 0 ? 1 : 0 ))
