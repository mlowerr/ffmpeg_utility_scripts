#!/bin/bash
# Audio Transcode-All Driver Script
# =================================
# Runs FLAC and WAV to MP3 conversion scripts in order.
#
# USAGE:
#   ./transcode_all_audio.sh                         # Process current directory only
#   ./transcode_all_audio.sh -r                      # Process recursively from current directory
#   ./transcode_all_audio.sh -t 4                    # Limit FFmpeg worker threads
#   ./transcode_all_audio.sh --quality 2             # Forward MP3 quality setting
#   ./transcode_all_audio.sh --config config.json    # Use a transcode CLI config file
#   ./transcode_all_audio.sh --skip-dir archive      # Skip a directory during recursive scans
#
# Hardware encoder flags are intentionally not supported for MP3 audio conversion.

set -u
shopt -s nullglob nocaseglob

FAILED_COUNT=0
RECURSE=false
THREADS=""
QUALITY=""
CONFIG=""
SKIP_DIRS=()
usage() {
    echo "Usage: $0 [-r] [-t threads] [--quality n] [--config path] [--skip-dir path]"
}

need_value() {
    if [[ $# -lt 2 || -z "${2:-}" ]]; then
        printf 'Error: %s requires a value.\n' "$1" >&2
        usage >&2
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--recurse) RECURSE=true; shift ;;
        -t|--threads) need_value "$1" "${2-}"; THREADS="$2"; shift 2 ;;
        --quality) need_value "$1" "${2-}"; QUALITY="$2"; shift 2 ;;
        --config) need_value "$1" "${2-}"; CONFIG="$2"; shift 2 ;;
        --skip-dir) need_value "$1" "${2-}"; SKIP_DIRS+=("$2"); shift 2 ;;
        -h|--help) usage; exit 0 ;;
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
[[ -n "$THREADS" ]] && child_args+=("--threads" "$THREADS")
[[ -n "$QUALITY" ]] && child_args+=("--quality" "$QUALITY")
[[ -n "$CONFIG" ]] && child_args+=("--config" "$CONFIG")
for d in "${SKIP_DIRS[@]}"; do
    child_args+=("--skip-dir" "$d")
done

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
