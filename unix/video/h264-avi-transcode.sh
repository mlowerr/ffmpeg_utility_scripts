#!/bin/bash
set -u
shopt -s nullglob
shopt -s nocaseglob
RECURSE=false
HW="software"
THREADS=""
QUALITY=""
CONFIG=""
CUDA_DECODE=false
RESUME=false
SEGMENT_DURATION=""
SKIP_DIRS=()
usage() {
  echo "Usage: $0 [-r] [-q|-n|-a] [-t threads] [--quality n] [--config path] [--skip-dir path] [-c|--cuda-decode] [--resume] [--segment-duration seconds]"
}
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
    *) usage >&2; exit 1 ;;
  esac
done
args=(--profile h264_avi)
[[ "$RECURSE" == true ]] && args+=(--recurse)
args+=(--hw "$HW")
[[ -n "$THREADS" ]] && args+=(--threads "$THREADS")
[[ -n "$QUALITY" ]] && args+=(--quality "$QUALITY")
[[ -n "$CONFIG" ]] && args+=(--config "$CONFIG")
[[ "$CUDA_DECODE" == true ]] && args+=(--cuda-decode)
[[ "$RESUME" == true ]] && args+=(--resume)
[[ -n "$SEGMENT_DURATION" ]] && args+=(--segment-duration "$SEGMENT_DURATION")
for d in "${SKIP_DIRS[@]}"; do
  args+=(--skip-dir "$d")
done
exec python3 "$(dirname "$0")/../../cross-platform/transcode_cli.py" "${args[@]}"
