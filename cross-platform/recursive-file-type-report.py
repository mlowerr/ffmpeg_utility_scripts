#!/usr/bin/env python3
"""Generate per-folder file type count reports for a directory tree."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the file type report for each folder in a target directory tree."
    )
    parser.add_argument(
        "target_directory",
        type=Path,
        help="Directory tree to scan for per-folder file type reports.",
    )
    return parser.parse_args()


def load_file_type_report_module() -> ModuleType:
    """Load sibling file-type-report.py so this script reuses its report formatting."""
    module_path = Path(__file__).with_name("file-type-report.py")
    spec = importlib.util.spec_from_file_location("file_type_report", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_directories(target_directory: Path) -> list[Path]:
    """Return the target directory and all child directories in stable path order."""
    directories = [target_directory]
    directories.extend(path for path in target_directory.rglob("*") if path.is_dir())
    return sorted(directories, key=lambda path: str(path).lower())


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
        file_type_report = load_file_type_report_module()
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    directories = iter_directories(target_directory)
    for index, directory in enumerate(directories):
        if index > 0:
            print("\n" + "=" * 72 + "\n")
        counts = file_type_report.count_file_types(directory, recursive=False)
        file_type_report.print_report(directory, False, counts)

    return 0


if __name__ == "__main__":
    sys.exit(main())
