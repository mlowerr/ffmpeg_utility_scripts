#!/usr/bin/env python3
"""List full paths for files matching a requested extension."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

NO_EXTENSION_LABEL = "[no extension]"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List full file paths for files with a requested extension."
    )
    parser.add_argument(
        "target_directory",
        type=Path,
        help="Directory to scan for matching files.",
    )
    parser.add_argument(
        "extension",
        help=(
            "Extension to match, with or without a leading dot (for example: mp4 or .mp4). "
            f"Use {NO_EXTENSION_LABEL!r} to match files without an extension."
        ),
    )
    parser.add_argument(
        "-r",
        "--recursive",
        "--recurse",
        action="store_true",
        help="Scan the target directory recursively.",
    )
    return parser.parse_args()


def normalize_extension(extension: str) -> str:
    """Return a stable, case-insensitive extension label for matching."""
    normalized = extension.strip().lower()
    if normalized == NO_EXTENSION_LABEL:
        return normalized
    if not normalized:
        raise ValueError("extension must not be empty")
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


def normalize_file_type(file_path: Path) -> str:
    """Return a stable, case-insensitive file type label for a path."""
    suffix = file_path.suffix.lower()
    if not suffix:
        return NO_EXTENSION_LABEL
    return suffix


def find_matching_files(target_directory: Path, extension: str, recursive: bool) -> list[Path]:
    """Return sorted regular files that match the normalized extension."""
    discovery = target_directory.rglob("*") if recursive else target_directory.glob("*")
    matches = [
        path.resolve()
        for path in discovery
        if path.is_file() and normalize_file_type(path) == extension
    ]
    return sorted(matches, key=lambda path: str(path).lower())


def main() -> int:
    args = parse_args()
    target_directory = args.target_directory.expanduser().resolve()

    if not target_directory.exists():
        print(f"Error: target directory does not exist: {target_directory}", file=sys.stderr)
        return 1
    if not target_directory.is_dir():
        print(f"Error: target path is not a directory: {target_directory}", file=sys.stderr)
        return 1

    try:
        extension = normalize_extension(args.extension)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    for path in find_matching_files(target_directory, extension, args.recursive):
        print(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
