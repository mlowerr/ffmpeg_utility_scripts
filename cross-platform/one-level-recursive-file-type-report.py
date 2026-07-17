#!/usr/bin/env python3
"""Combine detailed recursive file type reports for each direct child folder."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

DEFAULT_REPORT_NAME = "recursive-file-type-report.txt"


@dataclass(frozen=True)
class AggregateStats:
    """Status totals and completed folders produced by a single tree scan."""

    total: int = 0
    temporary: int = 0
    transcoded: int = 0
    remaining: int = 0
    folders_with_no_remaining: tuple[Path, ...] = ()


@dataclass(frozen=True)
class DirectoryReport:
    """Precomputed report values for one scanned directory."""

    child_directory: Path
    directory: Path
    counts: object
    detailed_stats: dict[str, object]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run detailed recursive file type reports for each direct child "
            "folder of the current working directory and combine the output."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Detailed report output path. Defaults to "
            "recursive-file-type-report.txt in the current directory."
        ),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Summary output path. Defaults to the detailed filename with -summary appended.",
    )
    parser.add_argument(
        "--all-file-types",
        action="store_true",
        help="Report every file type instead of only configured video profile types.",
    )
    return parser.parse_args(argv)


def load_module(script_name: str, module_name: str) -> ModuleType:
    """Load a sibling Python script as a module."""
    module_path = Path(__file__).with_name(script_name)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def iter_child_directories(root_directory: Path) -> list[Path]:
    """Return direct child directories of root_directory in stable path order."""
    return sorted(
        (path for path in root_directory.iterdir() if path.is_dir()),
        key=lambda path: path.name.lower(),
    )


def derive_summary_path(output_path: Path) -> Path:
    """Return a distinct summary filename alongside the detailed report."""
    return output_path.with_name(f"{output_path.stem}-summary{output_path.suffix}")


def video_extensions() -> set[str]:
    """Get video extensions from the canonical transcoding profiles."""
    transcode_cli = load_module("transcode_cli.py", "transcode_cli_for_file_report")
    return {
        profile["ext"].lower()
        for profile in transcode_cli.PROFILES.values()
        if profile["mode"] == "video"
    }


def scan_reports(
    root_directory: Path,
    excluded_paths: set[Path],
    all_file_types: bool,
) -> tuple[list[Path], list[DirectoryReport], AggregateStats]:
    """Traverse the tree once and compute detailed and aggregate report data."""
    recursive_report = load_module(
        "recursive-file-type-report.py", "recursive_file_type_report"
    )
    file_type_report = recursive_report.load_file_type_report_module()
    allowed_extensions = None if all_file_types else video_extensions()
    child_directories = iter_child_directories(root_directory)
    reports: list[DirectoryReport] = []
    total = temporary = transcoded = remaining = 0
    no_remaining: list[Path] = []

    for child_directory in child_directories:
        files = [
            path
            for path in file_type_report.discover_files(child_directory, recursive=True)
            if path.resolve() not in excluded_paths
            and (
                allowed_extensions is None or path.suffix.lower() in allowed_extensions
            )
        ]
        counts = file_type_report.count_file_types(files)
        detailed_stats = file_type_report.collect_detailed_stats(files)
        directory_remaining = sum(stats.remaining for stats in detailed_stats.values())
        total += sum(stats.total for stats in detailed_stats.values())
        temporary += sum(stats.temporary for stats in detailed_stats.values())
        transcoded += sum(stats.transcoded for stats in detailed_stats.values())
        remaining += directory_remaining
        if directory_remaining == 0:
            no_remaining.append(child_directory)
        reports.append(
            DirectoryReport(child_directory, child_directory, counts, detailed_stats)
        )

    return (
        child_directories,
        reports,
        AggregateStats(total, temporary, transcoded, remaining, tuple(no_remaining)),
    )


def write_combined_report(
    output_path: Path,
    root_directory: Path,
    child_directories: list[Path],
    reports: list[DirectoryReport],
    file_type_report: ModuleType,
) -> None:
    """Write precomputed detailed recursive reports."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as report_file:
        with contextlib.redirect_stdout(report_file):
            print(f"Combined detailed recursive file type report for: {root_directory}")
            print(f"Direct child folders scanned: {len(child_directories)}")
            if not child_directories:
                print("\nNo direct child folders found.")
                return

            for index, report in enumerate(reports):
                if index > 0:
                    print("\n" + "#" * 72 + "\n")
                print(f"Child folder report for: {report.child_directory}")
                file_type_report.print_report(
                    report.directory, True, report.counts, report.detailed_stats
                )


def write_summary_report(
    summary_path: Path, root_directory: Path, aggregate: AggregateStats
) -> None:
    """Write aggregate status totals without a per-extension table."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as summary_file:
        print(f"Combined file type summary for: {root_directory}", file=summary_file)
        print(f"Total: {aggregate.total}", file=summary_file)
        print(f"Temporary: {aggregate.temporary}", file=summary_file)
        print(f"Transcoded: {aggregate.transcoded}", file=summary_file)
        print(f"Remaining: {aggregate.remaining}", file=summary_file)
        print("\nFolders with no files left to transcode:", file=summary_file)
        if aggregate.folders_with_no_remaining:
            for directory in aggregate.folders_with_no_remaining:
                print(directory, file=summary_file)
        else:
            print("None", file=summary_file)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_directory = Path.cwd().resolve()
    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else root_directory / DEFAULT_REPORT_NAME
    )
    summary_path = (
        args.summary_output.expanduser().resolve()
        if args.summary_output is not None
        else derive_summary_path(output_path)
    )
    if output_path == summary_path:
        print(
            "Error: detailed and summary output paths must be different",
            file=sys.stderr,
        )
        return 1

    try:
        child_directories, reports, aggregate = scan_reports(
            root_directory, {output_path, summary_path}, args.all_file_types
        )
        recursive_report = load_module(
            "recursive-file-type-report.py", "recursive_file_type_report_writer"
        )
        file_type_report = recursive_report.load_file_type_report_module()
        write_combined_report(
            output_path, root_directory, child_directories, reports, file_type_report
        )
        write_summary_report(summary_path, root_directory, aggregate)
    except OSError as error:
        print(f"Error: could not write report: {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote combined report: {output_path}")
    print(f"Wrote summary report: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
