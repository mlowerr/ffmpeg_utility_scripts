#!/bin/bash
set -u
shopt -s nullglob
shopt -s nocaseglob

resolve_script_dir() {
    local source="${BASH_SOURCE[0]}"

    while [[ -L "$source" ]]; do
        local source_dir
        source_dir=$(cd -P -- "$(dirname -- "$source")" && pwd)
        source=$(readlink "$source")
        [[ "$source" == /* ]] || source="$source_dir/$source"
    done

    cd -P -- "$(dirname -- "$source")" && pwd
}

script_dir=""
script_dir=$(resolve_script_dir)
exec bash "$script_dir/../../cross-platform/transcode-cli.sh" h264_flv "$@"
