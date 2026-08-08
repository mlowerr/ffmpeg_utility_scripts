#!/bin/bash
# Generic transcode_cli.py wrapper.
# Usage: transcode-cli.sh <profile> [-r] [-q|-n|-a] [-t threads] [--quality n] [--config path] [--skip-dir path] [-c|--cuda-decode] [--resume] [--segment-duration seconds] [directory]
# This script is the single parsing implementation behind every unix/video, unix/audio,
# and unix/mkv-shrink wrapper.

set -u
shopt -s nullglob
shopt -s nocaseglob

usage() {
    echo "Usage: $0 <profile> [-r] [-q|-n|-a] [-t threads] [--quality n] [--config path] [--skip-dir path] [-c|--cuda-decode] [--resume] [--segment-duration seconds] [directory]"
}

PROFILE="${1:-}"
if [[ -z "$PROFILE" ]]; then
    usage >&2
    exit 1
fi
shift
if [[ "$PROFILE" == "-h" || "$PROFILE" == "--help" ]]; then
    usage
    exit 0
fi

RECURSE=false
HW="software"
THREADS=""
QUALITY=""
CONFIG=""
CUDA_DECODE=false
RESUME=false
SEGMENT_DURATION=""
SEARCH_DIR=""
SKIP_DIRS=()

need_value() {
    if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: $1 requires a value." >&2
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
        --resume) RESUME=true; shift ;;
        --segment-duration) need_value "$1" "${2-}"; SEGMENT_DURATION="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        -*) usage >&2; exit 1 ;;
        *) SEARCH_DIR="$1"; shift ;;
    esac
done

args=(--profile "$PROFILE")
[[ "$RECURSE" == true ]] && args+=(--recurse)
args+=(--hw "$HW")
[[ -n "$THREADS" ]] && args+=(--threads "$THREADS")
[[ -n "$QUALITY" ]] && args+=(--quality "$QUALITY")
[[ -n "$CONFIG" ]] && args+=(--config "$CONFIG")
[[ -n "$SEARCH_DIR" ]] && args+=(--path "$SEARCH_DIR")
[[ "$CUDA_DECODE" == true ]] && args+=(--cuda-decode)
[[ "$RESUME" == true ]] && args+=(--resume)
[[ -n "$SEGMENT_DURATION" ]] && args+=(--segment-duration "$SEGMENT_DURATION")
for d in "${SKIP_DIRS[@]}"; do
    args+=(--skip-dir "$d")
done
exec python3 "$(dirname "$0")/transcode_cli.py" "${args[@]}"