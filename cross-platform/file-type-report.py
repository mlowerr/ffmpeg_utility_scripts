#!/usr/bin/env python3
"""Generate a cross-platform file type count report for a directory."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

NO_EXTENSION_LABEL = "[no extension]"
TRANSCODED_MARKER = "_REDU"
TEMPORARY_MARKER = ".tmp"


@dataclass(frozen=True)
class FileTypeStats:
    """Detailed counts for a normalized file type."""

    total: int = 0
    temporary: int = 0
    transcoded: int = 0
    remaining: int = 0


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
    parser.add_argument(
        "-d",
        "--detailed",
        action="store_true",
        help=(
            "Include temporary (.tmp...), already-transcoded (_REDU), and "
            "remaining-to-transcode counts for each file type."
        ),
    )
    return parser.parse_args()


def normalize_file_type(file_path: Path) -> str:
    """Return a stable, case-insensitive file type label for a path."""
    suffix = file_path.suffix.lower()
    if not suffix:
        return NO_EXTENSION_LABEL
    return suffix


def is_temporary_file(file_path: Path) -> bool:
    """Return True when the file name contains a temporary .tmp marker."""
    return TEMPORARY_MARKER in file_path.name.lower()


def is_transcoded_file(file_path: Path) -> bool:
    """Return True when the file name contains the transcoded _REDU marker."""
    return TRANSCODED_MARKER.lower() in file_path.name.lower()


def discover_files(target_directory: Path, recursive: bool) -> list[Path]:
    """Return regular files found in the requested target directory."""
    discovery = target_directory.rglob("*") if recursive else target_directory.glob("*")
    return [path for path in discovery if path.is_file()]


def count_file_types(
    target_directory_or_files: Path | list[Path], recursive: bool = False
) -> Counter[str]:
    """Count regular files by normalized file extension.

    Accepts either a pre-discovered file list or a target directory with the
    legacy recursive flag used by recursive-file-type-report.py.
    """
    if isinstance(target_directory_or_files, Path):
        files = discover_files(target_directory_or_files, recursive)
    else:
        files = target_directory_or_files

    counts: Counter[str] = Counter()

    for path in files:
        counts[normalize_file_type(path)] += 1

    return counts


def collect_detailed_stats(files: list[Path]) -> dict[str, FileTypeStats]:
    """Collect total, temporary, transcoded, and remaining counts by file type."""
    totals: Counter[str] = Counter()
    temporary: Counter[str] = Counter()
    transcoded: Counter[str] = Counter()
    remaining: Counter[str] = Counter()

    for path in files:
        file_type = normalize_file_type(path)
        is_temporary = is_temporary_file(path)
        is_transcoded = is_transcoded_file(path)

        totals[file_type] += 1
        if is_temporary:
            temporary[file_type] += 1
        if is_transcoded:
            transcoded[file_type] += 1
        if not is_temporary and not is_transcoded:
            remaining[file_type] += 1

    return {
        file_type: FileTypeStats(
            total=total,
            temporary=temporary[file_type],
            transcoded=transcoded[file_type],
            remaining=remaining[file_type],
        )
        for file_type, total in totals.items()
    }


def print_report(
    target_directory: Path,
    recursive: bool,
    counts: Counter[str],
    detailed_stats: dict[str, FileTypeStats] | None = None,
) -> None:
    total_files = sum(counts.values())
    scan_mode = "recursive" if recursive else "single directory"

    print(f"File type report for: {target_directory}")
    print(f"Scan mode: {scan_mode}")
    print(f"Total files: {total_files}")

    if total_files == 0:
        print("\nNo files found.")
        return

    sorted_counts = sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    print("\nFile Type          Count")
    print("----------------  -----")
    for file_type, count in sorted_counts:
        print(f"{file_type:<16}  {count:>5}")

    if detailed_stats is None:
        return

    print("\nDetailed file type report")
    print("File Type          Count  Temporary  Transcoded  Remaining")
    print("----------------  -----  ---------  ----------  ---------")
    for file_type, count in sorted_counts:
        stats = detailed_stats[file_type]
        print(
            f"{file_type:<16}  {count:>5}  "
            f"{stats.temporary:>9}  {stats.transcoded:>10}  {stats.remaining:>9}"
        )


def main() -> int:
    args = parse_args()
    target_directory = args.target_directory.expanduser().resolve()

    if not target_directory.exists():
        print(f"Error: target directory does not exist: {target_directory}", file=sys.stderr)
        return 1
    if not target_directory.is_dir():
        print(f"Error: target path is not a directory: {target_directory}", file=sys.stderr)
        return 1

    files = discover_files(target_directory, args.recursive)
    counts = count_file_types(files)
    detailed_stats = collect_detailed_stats(files) if args.detailed else None
    print_report(target_directory, args.recursive, counts, detailed_stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
