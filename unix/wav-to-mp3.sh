#!/bin/bash
# WAV to 256k MP3 Conversion Script
# ======================================
# Converts .wav audio files in the current directory (or recursively with -r)
# to 256 kbps MP3 files using ffmpeg/libmp3lame.

set -u
shopt -s nullglob nocaseglob

FAILED_COUNT=0
RECURSE=false

while getopts "r" opt; do
    case $opt in
        r) RECURSE=true ;;
        *) echo "Usage: $0 [-r]"; exit 1 ;;
    esac
done

temp_output=""
trap 'rm -f -- "$temp_output"; exit' INT TERM EXIT

sanitize_filename() {
    printf '%q' "$1"
}

rename_files() {
    local dir="$1"
    for f in "$dir"/*" "*.[Ww][Aa][Vv]; do
        [[ -f "$f" ]] || continue

        local filename new_filename new_name
        filename=$(basename "$f")
        new_filename="${filename// /_}"
        new_name="$dir/$new_filename"

        [[ "$f" == "$new_name" ]] && continue

        if ! mv -n -v -- "$f" "$new_name" 2>/dev/null; then
            echo "Warning: Failed to rename '$f' -> '$new_name' (target exists or error)" >&2
        fi
    done
}

stream_count() {
    local selector="$1"
    local path="$2"
    ffprobe -v error -select_streams "$selector" -show_entries stream=index \
        -of csv=p=0 -- "$path" 2>/dev/null | wc -l
}

process_file() {
    local f="$1"
    local current="$2"
    local total="$3"
    local dir base_name output temp_out input_audio_streams output_audio_streams

    if [[ "$f" == *$'\n'* ]]; then
        echo "Warning: Skipping file with newline in name: $(sanitize_filename "$f")" >&2
        return
    fi

    dir=$(dirname "$f")
    base_name=$(basename "$f")
    base_name="${base_name%.[Ww][Aa][Vv]}"
    output="$dir/${base_name}.mp3"
    temp_out="$dir/${base_name}.tmp.mp3"

    rm -f -- "$temp_out"
    temp_output="$temp_out"

    printf '\n\nProcessing file %s of %s\n\n' "$current" "$total"
    printf 'Converting %q to 256k MP3...\n' "$f"

    if ffmpeg -hide_banner -loglevel warning -stats \
            -i "$f" \
            -vn \
            -map "0:a:0?" \
            -c:a libmp3lame \
            -b:a 256k \
            -map_metadata 0 \
            -id3v2_version 3 \
            -y \
            "$temp_out"; then
        printf '\n\n'
        if [[ ! -s "$temp_out" ]]; then
            echo "Error: Temporary output '$temp_out' is empty. Keeping source." >&2
            rm -f -- "$temp_out"
            ((FAILED_COUNT++))
            temp_output=""
            return
        fi

        if ! ffprobe -v error -- "$temp_out" >/dev/null 2>&1; then
            echo "Error: Output verification failed for '$f'. Keeping source." >&2
            rm -f -- "$temp_out"
            ((FAILED_COUNT++))
            temp_output=""
            return
        fi

        input_audio_streams=$(stream_count a "$f")
        output_audio_streams=$(stream_count a "$temp_out")
        if [[ "$input_audio_streams" -gt 0 && "$output_audio_streams" -lt 1 ]]; then
            echo "Error: No audio stream found in output for '$f'. Keeping source." >&2
            rm -f -- "$temp_out"
            ((FAILED_COUNT++))
            temp_output=""
            return
        fi

        if mv -n -- "$temp_out" "$output"; then
            if rm -- "$f"; then
                echo "Successfully converted '$f' to '$output'. Source deleted."
            else
                echo "Warning: Converted '$f' but failed to remove source." >&2
                ((FAILED_COUNT++))
            fi
        else
            echo "Error: Failed to move '$temp_out' to '$output' (target exists or error). Keeping source." >&2
            rm -f -- "$temp_out"
            ((FAILED_COUNT++))
        fi
    else
        printf '\n\n'
        echo "Error: ffmpeg failed on '$f'. Keeping source." >&2
        rm -f -- "$temp_out"
        ((FAILED_COUNT++))
    fi

    temp_output=""
}

if [[ "$RECURSE" == true ]]; then
    while IFS= read -r -d '' dir; do
        rename_files "$dir"
    done < <(find . -type d -print0)
else
    rename_files "."
fi

files_to_process=()
if [[ "$RECURSE" == true ]]; then
    while IFS= read -r -d '' f; do
        [[ -f "$f" ]] || continue
        output="${f%.[Ww][Aa][Vv]}.mp3"
        [[ -e "$output" ]] && continue
        files_to_process+=("$f")
    done < <(find . -type f -iname '*.wav' -print0)
else
    for f in *.[Ww][Aa][Vv]; do
        [[ -f "$f" ]] || continue
        output="${f%.[Ww][Aa][Vv]}.mp3"
        [[ -e "$output" ]] && continue
        files_to_process+=("$f")
    done
fi

total_files=${#files_to_process[@]}
if [[ "$total_files" -eq 0 ]]; then
    echo "No eligible WAV files found to process."
    exit 0
fi

file_index=0
for f in "${files_to_process[@]}"; do
    ((file_index++))
    process_file "$f" "$file_index" "$total_files"
done

exit $(( FAILED_COUNT > 0 ? 1 : 0 ))
