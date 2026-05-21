#!/bin/bash
set -u
shopt -s nullglob
shopt -s nocaseglob
RECURSE=false
HW="software"
THREADS=""
QUALITY=""
CONFIG=""
SKIP_DIRS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -r|--recurse) RECURSE=true; shift ;;
    -q) HW="qsv"; shift ;;
    -n) HW="nvenc"; shift ;;
    -a) HW="amf"; shift ;;
    -t|--threads) THREADS="$2"; shift 2 ;;
    --quality) QUALITY="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --skip-dir) SKIP_DIRS+=("$2"); shift 2 ;;
    *) echo "Usage: $0 [-r] [-q|-n|-a] [-t threads] [--quality n] [--config path] [--skip-dir path]"; exit 1 ;;
  esac
done
args=(--profile hevc_mp4)
[[ "$RECURSE" == true ]] && args+=(--recurse)
args+=(--hw "$HW")
[[ -n "$THREADS" ]] && args+=(--threads "$THREADS")
[[ -n "$QUALITY" ]] && args+=(--quality "$QUALITY")
[[ -n "$CONFIG" ]] && args+=(--config "$CONFIG")
for d in "${SKIP_DIRS[@]}"; do
  args+=(--skip-dir "$d")
done
exec python3 "$(dirname "$0")/../cross-platform/transcode_cli.py" "${args[@]}"
