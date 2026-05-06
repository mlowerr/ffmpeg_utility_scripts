#!/usr/bin/env python3
"""Generate a cross-platform file type count report for a directory."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

NO_EXTENSION_LABEL = "[no extension]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report the total number of files by file type in a target directory."
    )
    parser.add_argument(
        "target_directory",
        type=Path,
        help="Directory to scan for files.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        "--recurse",
        action="store_true",
        help="Scan the target directory recursively.",
    )
    return parser.parse_args()


def normalize_file_type(file_path: Path) -> str:
    """Return a stable, case-insensitive file type label for a path."""
    suffix = file_path.suffix.lower()
    if not suffix:
        return NO_EXTENSION_LABEL
    return suffix


def count_file_types(target_directory: Path, recursive: bool) -> Counter[str]:
    """Count regular files by normalized file extension."""
    discovery = target_directory.rglob("*") if recursive else target_directory.glob("*")
    counts: Counter[str] = Counter()

    for path in discovery:
        if path.is_file():
            counts[normalize_file_type(path)] += 1

    return counts


def print_report(target_directory: Path, recursive: bool, counts: Counter[str]) -> None:
    total_files = sum(counts.values())
    scan_mode = "recursive" if recursive else "single directory"

    print(f"File type report for: {target_directory}")
    print(f"Scan mode: {scan_mode}")
    print(f"Total files: {total_files}")

    if total_files == 0:
        print("\nNo files found.")
        return

    print("\nFile Type          Count")
    print("----------------  -----")
    for file_type, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"{file_type:<16}  {count:>5}")


def main() -> int:
    args = parse_args()
    target_directory = args.target_directory.expanduser().resolve()

    if not target_directory.exists():
        print(f"Error: target directory does not exist: {target_directory}", file=sys.stderr)
        return 1
    if not target_directory.is_dir():
        print(f"Error: target path is not a directory: {target_directory}", file=sys.stderr)
        return 1

    counts = count_file_types(target_directory, args.recursive)
    print_report(target_directory, args.recursive, counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
