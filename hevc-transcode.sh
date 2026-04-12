#!/bin/bash
set -u

shopt -s nullglob nocaseglob

temp_output=""
trap 'rm -f -- "$temp_output"; exit' INT TERM EXIT

# 1. Rename files: replace literal spaces with underscores
for f in *" "*; do
    [[ -f "$f" ]] || continue

    new_name="${f// /_}"

    if [[ -e "$new_name" && "$f" != "$new_name" ]]; then
        echo "Skipping rename: '$f' -> '$new_name' (target already exists)"
        continue
    fi

    mv -v -- "$f" "$new_name"
done

# 2. Transcode logic
for f in *.mp4; do
    [[ -f "$f" ]] || continue

    # Skip already-transcoded files
    [[ "$f" == *_HEVC.mp4 ]] && continue

    output="${f%.*}_HEVC.mp4"
    temp_output="${f%.*}_HEVC.tmp.mp4"

    if [[ -e "$output" ]]; then
        echo "Skipping '$f': '$output' already exists."
        continue
    fi

    rm -f -- "$temp_output"

    echo "Transcoding '$f'..."
    if ffmpeg -i "$f" -map 0 -c:v libx265 -crf 28 -preset medium -c:a copy "$temp_output"; then
        if [[ -s "$temp_output" ]]; then
            mv -- "$temp_output" "$output"
            rm -- "$f"
            echo "Successfully transcoded '$f' to '$output'. Source deleted."
        else
            echo "Error: Temporary output '$temp_output' is empty. Keeping source '$f'."
            rm -f -- "$temp_output"
        fi
    else
        echo "Error: ffmpeg failed on '$f'. Keeping source."
        rm -f -- "$temp_output"
    fi
done
