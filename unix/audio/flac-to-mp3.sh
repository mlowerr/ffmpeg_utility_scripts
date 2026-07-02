#!/bin/bash
set -u
shopt -s nullglob
shopt -s nocaseglob
RECURSE=false
THREADS=""
QUALITY=""
CONFIG=""
SKIP_DIRS=()
need_value() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "Error: $1 requires a value." >&2
    echo "Usage: $0 [-r] [-t threads] [--quality n] [--config path] [--skip-dir path]" >&2
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
    *) echo "Usage: $0 [-r] [-t threads] [--quality n] [--config path] [--skip-dir path]"; exit 1 ;;
  esac
done
args=(--profile flac_mp3)
[[ "$RECURSE" == true ]] && args+=(--recurse)
[[ -n "$THREADS" ]] && args+=(--threads "$THREADS")
[[ -n "$QUALITY" ]] && args+=(--quality "$QUALITY")
[[ -n "$CONFIG" ]] && args+=(--config "$CONFIG")
for d in "${SKIP_DIRS[@]}"; do
  args+=(--skip-dir "$d")
done
exec python3 "$(dirname "$0")/../../cross-platform/transcode_cli.py" "${args[@]}"
