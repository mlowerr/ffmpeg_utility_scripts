#!/usr/bin/env python3
"""Combine detailed recursive file type reports for each direct child folder."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

DEFAULT_REPORT_NAME = "recursive-file-type-report.txt"


def parse_args() -> argparse.Namespace:
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
            "Report output path. Defaults to recursive-file-type-report.txt "
            "in the directory where this wrapper is run."
        ),
    )
    return parser.parse_args()


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


def write_combined_report(output_path: Path, root_directory: Path) -> None:
    """Write detailed recursive reports for each direct child directory."""
    recursive_report = load_module(
        "recursive-file-type-report.py", "recursive_file_type_report"
    )
    file_type_report = recursive_report.load_file_type_report_module()
    child_directories = iter_child_directories(root_directory)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as report_file:
        with contextlib.redirect_stdout(report_file):
            print(f"Combined detailed recursive file type report for: {root_directory}")
            print(f"Direct child folders scanned: {len(child_directories)}")

            if not child_directories:
                print("\nNo direct child folders found.")
                return

            for child_index, child_directory in enumerate(child_directories):
                if child_index > 0:
                    print("\n" + "#" * 72 + "\n")
                print(f"Child folder report for: {child_directory}")
                directories = recursive_report.iter_directories(child_directory)
                for directory_index, directory in enumerate(directories):
                    if directory_index > 0:
                        print("\n" + "=" * 72 + "\n")
                    files = file_type_report.discover_files(directory, recursive=False)
                    counts = file_type_report.count_file_types(files)
                    detailed_stats = file_type_report.collect_detailed_stats(files)
                    file_type_report.print_report(
                        directory,
                        False,
                        counts,
                        detailed_stats,
                    )


def main() -> int:
    args = parse_args()
    root_directory = Path.cwd().resolve()
    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else root_directory / DEFAULT_REPORT_NAME
    )

    try:
        write_combined_report(output_path, root_directory)
    except OSError as error:
        print(f"Error: could not write report: {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote combined report: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
