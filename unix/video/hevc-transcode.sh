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
SKIP_DIRS=()
usage() {
  echo "Usage: $0 [-r] [-q|-n|-a] [-t threads] [--quality n] [--config path] [--skip-dir path] [--cuda-decode]"
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
    --cuda-decode) CUDA_DECODE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 1 ;;
  esac
done
args=(--profile hevc_mp4)
[[ "$RECURSE" == true ]] && args+=(--recurse)
args+=(--hw "$HW")
[[ -n "$THREADS" ]] && args+=(--threads "$THREADS")
[[ -n "$QUALITY" ]] && args+=(--quality "$QUALITY")
[[ -n "$CONFIG" ]] && args+=(--config "$CONFIG")
[[ "$CUDA_DECODE" == true ]] && args+=(--cuda-decode)
for d in "${SKIP_DIRS[@]}"; do
  args+=(--skip-dir "$d")
done
exec python3 "$(dirname "$0")/../../cross-platform/transcode_cli.py" "${args[@]}"
