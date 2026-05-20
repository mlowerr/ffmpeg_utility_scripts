#!/bin/bash
set -u
shopt -s nullglob
shopt -s nocaseglob
RECURSE=false
HW="software"
THREADS=""
while getopts "rqnat:" opt; do
  case "$opt" in
    r) RECURSE=true ;;
    q) HW="qsv" ;;
    n) HW="nvenc" ;;
    a) HW="amf" ;;
    t) THREADS="$OPTARG" ;;
    *) echo "Usage: $0 [-r] [-q|-n|-a] [-t threads]"; exit 1 ;;
  esac
done
args=(--profile h264_avi)
[[ "$RECURSE" == true ]] && args+=(--recurse)
args+=(--hw "$HW")
[[ -n "$THREADS" ]] && args+=(--threads "$THREADS")
exec python3 "$(dirname "$0")/../cross-platform/transcode_cli.py" "${args[@]}"
