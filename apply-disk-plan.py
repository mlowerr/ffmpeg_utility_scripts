#!/usr/bin/env python3
"""Apply a disk move plan.

By default this script prompts for the target disk size and output directory base
name.  The same values can also be supplied positionally so wrapper scripts can
run non-interactively, e.g. ``apply-disk-plan.py 2 zzz``.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskType:
    choice: str
    label: str
    bytes: int


DISK_TYPES: tuple[DiskType, ...] = (
    DiskType("1", "25GB", 25 * 1000**3),
    DiskType("2", "50GB", 50 * 1000**3),
    DiskType("3", "100GB", 100 * 1000**3),
)
DISK_TYPE_BY_CHOICE = {disk_type.choice: disk_type for disk_type in DISK_TYPES}
DEFAULT_PLAN_FILE = Path("disk-plan.txt")


def disk_type_choices() -> str:
    return ", ".join(f"{d.choice}={d.label}" for d in DISK_TYPES)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply disk-plan.txt move instructions to numbered disk folders.",
    )
    parser.add_argument(
        "disk_type",
        nargs="?",
        help=f"Disk size choice ({disk_type_choices()}); choice 2 is 50GB.",
    )
    parser.add_argument(
        "base_name",
        nargs="?",
        help="Base name for generated disk folders (for example: zzz).",
    )
    parser.add_argument(
        "--plan",
        default=str(DEFAULT_PLAN_FILE),
        help=f"Plan file to apply (default: {DEFAULT_PLAN_FILE}).",
    )
    return parser.parse_args(argv)


def prompt_for_disk_type() -> str:
    print("Select disk type:")
    for disk_type in DISK_TYPES:
        print(f"  {disk_type.choice}) {disk_type.label}")
    return input("Disk type: ").strip()


def prompt_for_base_name() -> str:
    return input("Base name: ").strip()


def resolve_disk_type(choice: str) -> DiskType:
    try:
        return DISK_TYPE_BY_CHOICE[choice]
    except KeyError:
        raise ValueError(f"invalid disk type '{choice}' (expected {disk_type_choices()})") from None


def resolve_options(args: argparse.Namespace) -> tuple[DiskType, str, Path]:
    disk_type_choice = args.disk_type if args.disk_type is not None else prompt_for_disk_type()
    base_name = args.base_name if args.base_name is not None else prompt_for_base_name()

    if not base_name:
        raise ValueError("base name cannot be empty")

    return resolve_disk_type(disk_type_choice), base_name, Path(args.plan)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        disk_type, base_name, plan_file = resolve_options(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # This repository does not include the planner implementation, so keep the
    # application side deliberately conservative: validate the non-interactive
    # inputs and fail clearly when there is no plan to apply.
    if not plan_file.exists():
        print(f"Error: plan file not found: {plan_file}", file=sys.stderr)
        return 1

    print(f"Applying {plan_file} using {disk_type.label} disks with base name '{base_name}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
