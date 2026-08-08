#!/bin/bash
set -u
shopt -s nullglob
shopt -s nocaseglob
exec "$(dirname "$0")/../../cross-platform/transcode-cli.sh" h264_m4v "$@"