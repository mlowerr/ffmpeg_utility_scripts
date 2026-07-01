#!/bin/bash
# Audio Transcode-All Driver Script
# =================================
# Runs FLAC and WAV to MP3 conversion scripts in order.
#
# USAGE:
#   ./transcode_all_audio.sh      # Process current directory only
#   ./transcode_all_audio.sh -r   # Process recursively from current directory
#   ./transcode_all_audio.sh -n   # Forward NVIDIA NVENC selection to child scripts
#
# The recursive and NVENC flags are cascaded to each child script.

set -u
shopt -s nullglob nocaseglob

FAILED_COUNT=0
RECURSE=false
USE_NVENC=false

usage() {
    echo "Usage: $0 [-r] [-n]"
}

while getopts "rnh" opt; do
    case "$opt" in
        r) RECURSE=true ;;
        n) USE_NVENC=true ;;
        h) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done

resolve_script_dir() {
    local source="${BASH_SOURCE[0]}"

    while [[ -L "$source" ]]; do
        local source_dir
        source_dir=$(cd -P -- "$(dirname -- "$source")" && pwd)
        source=$(readlink "$source")

        if [[ "$source" != /* ]]; then
            source="$source_dir/$source"
        fi
    done

    cd -P -- "$(dirname -- "$source")" && pwd
}

script_dir=""
script_dir=$(resolve_script_dir)

child_args=()
if [[ "$RECURSE" == true ]]; then
    child_args+=("-r")
fi
if [[ "$USE_NVENC" == true ]]; then
    child_args+=("-n")
fi

run_child_script() {
    local script_name="$1"
    local script_path="$script_dir/$script_name"
    local status=0

    if [[ ! -f "$script_path" ]]; then
        printf 'Error: Required child script not found: %s\n' "$script_path" >&2
        ((FAILED_COUNT++))
        return
    fi

    if [[ ! -x "$script_path" ]]; then
        printf 'Warning: Child script is not executable; running with bash: %s\n' "$script_path" >&2
    fi

    printf '\n=== Running %s ===\n' "$script_name"
    if bash "$script_path" "${child_args[@]}"; then
        printf '=== Completed %s successfully ===\n' "$script_name"
    else
        status=$?
        printf 'Error: %s exited with status %s. Continuing with remaining scripts.\n' "$script_name" "$status" >&2
        ((FAILED_COUNT++))
    fi
}

run_child_script "flac-to-mp3.sh"
run_child_script "wav-to-mp3.sh"

exit $(( FAILED_COUNT > 0 ? 1 : 0 ))
