#!/usr/bin/env bash
# Build a disk plan, then apply it/move files. Optional plan variables are
# forwarded to apply-disk-plan when provided.

set -u
shopt -s nullglob nocaseglob

DISK_SIZE_TYPE="${DISK_SIZE_TYPE:-}"
BASE_NAME="${BASE_NAME:-}"
PLAN_FILE="${PLAN_FILE:-disk-plan.sh}"
DRY_RUN=false
APPLY_DISK_PLAN="${APPLY_DISK_PLAN:-./apply-disk-plan}"

usage() {
    cat <<USAGE
Usage: $0 [--disk-size-type type] [--base-name name] [--plan-file path] [--dry-run]

Options are forwarded to apply-disk-plan when present.
USAGE
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
        --disk-size-type|--disk-type|--type)
            need_value "$1" "${2-}"
            DISK_SIZE_TYPE="$2"
            shift 2
            ;;
        --base-name)
            need_value "$1" "${2-}"
            BASE_NAME="$2"
            shift 2
            ;;
        --plan-file)
            need_value "$1" "${2-}"
            PLAN_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Error: Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

apply_args=(--plan-file "$PLAN_FILE")
if [[ -n "$DISK_SIZE_TYPE" ]]; then
    apply_args+=(--disk-size-type "$DISK_SIZE_TYPE")
fi
if [[ -n "$BASE_NAME" ]]; then
    apply_args+=(--base-name "$BASE_NAME")
fi
if [[ "$DRY_RUN" == true ]]; then
    apply_args+=(--dry-run)
fi

"$APPLY_DISK_PLAN" "${apply_args[@]}"
