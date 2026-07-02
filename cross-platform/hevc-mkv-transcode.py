#!/usr/bin/env python3
"""Compatibility wrapper for the shared HEVC/H.265 MKV transcoder.

This script intentionally delegates to ``transcode_cli.py --profile hevc_mkv`` so
MKV HEVC processing uses the same candidate discovery, stream-preservation
checks, and no-overwrite finalization path as the shell/PowerShell wrappers.
Keep this wrapper behaviorally aligned with that shared profile rather than
reintroducing standalone transcoding logic here.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcode MKV files to HEVC/H.265")
    parser.add_argument("-r", "--recurse", action="store_true", help="Process recursively")
    parser.add_argument("-q", "--quick-sync", action="store_true", help="Use Intel Quick Sync")
    parser.add_argument("-n", "--nvenc", action="store_true", help="Use NVIDIA NVENC")
    parser.add_argument("-a", "--amf", action="store_true", help="Use AMD AMF")
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=0,
        help="Limit ffmpeg/x265 thread usage (positive integer, software mode recommended)",
    )
    parser.add_argument("--strict-cleanup", action="store_true", help="Treat source cleanup issues as hard failures")
    args = parser.parse_args(argv)
    if args.threads < 0:
        parser.error("--threads must be zero or a positive integer")
    selected_hw = [args.quick_sync, args.nvenc, args.amf]
    if sum(bool(value) for value in selected_hw) > 1:
        parser.error("choose only one hardware encoder option")
    return args


def build_transcode_cli_command(args: argparse.Namespace) -> list[str]:
    script_path = Path(__file__).with_name("transcode_cli.py")
    hw = "software"
    if args.quick_sync:
        hw = "qsv"
    elif args.nvenc:
        hw = "nvenc"
    elif args.amf:
        hw = "amf"

    command = [
        sys.executable,
        str(script_path),
        "--profile",
        "hevc_mkv",
        "--hw",
        hw,
    ]
    if args.recurse:
        command.append("--recurse")
    if args.threads:
        command.extend(["--threads", str(args.threads)])
    if args.strict_cleanup:
        command.append("--strict-cleanup")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    command = build_transcode_cli_command(args)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
