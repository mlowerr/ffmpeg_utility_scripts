#!/bin/bash
# Video Transcode-All Driver Script
# =================================
# Runs the AVI, FLV, MOV, MPG, RM, RMVB, WMV, and MP4 H.264 transcode scripts in order.
#
# USAGE:
#   ./transcode_all_video.sh      # Process current directory only
#   ./transcode_all_video.sh -r   # Process recursively from current directory
#   ./transcode_all_video.sh -n   # Use NVIDIA NVENC in child scripts
#   ./transcode_all_video.sh -n --cuda-decode  # Request CUDA decode with NVENC
#   ./transcode_all_video.sh -r --quality 24 --skip-dir ./archive
#
# Supported child-wrapper options are cascaded to each child script.

set -u
shopt -s nullglob nocaseglob

FAILED_COUNT=0
RECURSE=false
HW="software"
THREADS=""
QUALITY=""
CONFIG=""
CUDA_DECODE=false
SKIP_DIRS=()

usage() {
    echo "Usage: $0 [-r] [-q|-n|-a] [-t threads] [--quality n] [--config path] [--skip-dir path] [-c|--cuda-decode]"
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
        -q) HW="qsv"; shift ;;
        -n) HW="nvenc"; shift ;;
        -a) HW="amf"; shift ;;
        -t|--threads) need_value "$1" "${2-}"; THREADS="$2"; shift 2 ;;
        --quality) need_value "$1" "${2-}"; QUALITY="$2"; shift 2 ;;
        --config) need_value "$1" "${2-}"; CONFIG="$2"; shift 2 ;;
        --skip-dir) need_value "$1" "${2-}"; SKIP_DIRS+=("$2"); shift 2 ;;
        -c|--cuda-decode) CUDA_DECODE=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 1 ;;
    esac
done

# Resolve the driver location so child scripts are loaded next to this file,
# even when the driver is invoked from another working directory or via symlink.
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
case "$HW" in
    qsv) child_args+=("-q") ;;
    nvenc) child_args+=("-n") ;;
    amf) child_args+=("-a") ;;
esac
if [[ -n "$THREADS" ]]; then
    child_args+=("--threads" "$THREADS")
fi
if [[ -n "$QUALITY" ]]; then
    child_args+=("--quality" "$QUALITY")
fi
if [[ -n "$CONFIG" ]]; then
    child_args+=("--config" "$CONFIG")
fi
if [[ "$CUDA_DECODE" == true ]]; then
    child_args+=("--cuda-decode")
fi
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

run_child_script "h264-avi-transcode.sh"
run_child_script "h264-flv-transcode.sh"
run_child_script "h264-mov-transcode.sh"
run_child_script "h264-mpg-transcode.sh"
run_child_script "h264-rm-transcode.sh"
run_child_script "h264-rmvb-transcode.sh"
run_child_script "h264-wmv-transcode.sh"
run_child_script "h264-transcode.sh"

exit $(( FAILED_COUNT > 0 ? 1 : 0 ))
