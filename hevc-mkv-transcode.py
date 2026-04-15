#!/usr/bin/env python3
"""Cross-platform HEVC/H.265 MKV transcoder.

Transcodes .mkv files to HEVC while preserving primary video plus all
audio/subtitle streams, writing output as .mkv for simple and fast processing.
"""

from __future__ import annotations

import argparse
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

FAILED_COUNT = 0
TEMP_OUTPUT: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcode MKV files to HEVC/H.265")
    parser.add_argument("-r", "--recurse", action="store_true", help="Process recursively")
    parser.add_argument("-q", "--quick-sync", action="store_true", help="Use Intel Quick Sync")
    parser.add_argument("-n", "--nvenc", action="store_true", help="Use NVIDIA NVENC")
    parser.add_argument("-a", "--amf", action="store_true", help="Use AMD AMF")
    return parser.parse_args()


def resolve_encoder(args: argparse.Namespace) -> tuple[str, str, List[str]]:
    video_codec = "libx265"
    preset = "medium"
    quality_opts = ["-crf", "24"]

    if args.quick_sync:
        video_codec = "hevc_qsv"
        quality_opts = ["-global_quality", "24"]
    elif args.nvenc:
        video_codec = "hevc_nvenc"
        preset = "p4"
        quality_opts = ["-rc", "vbr", "-cq", "24"]
    elif args.amf:
        video_codec = "hevc_amf"
        preset = "speed"
        quality_opts = ["-qp_i", "24", "-qp_p", "24", "-qp_b", "24"]

    return video_codec, preset, quality_opts


def rename_files(files: Iterable[Path]) -> None:
    for file_path in files:
        if " " not in file_path.name:
            continue
        new_path = file_path.with_name(file_path.name.replace(" ", "_"))
        if new_path.exists():
            print(f"Warning: skipping rename '{file_path}' -> '{new_path}' (target exists)", file=sys.stderr)
            continue
        file_path.rename(new_path)
        print(f"Renamed: '{file_path}' -> '{new_path}'")


def collect_files(root: Path, recurse: bool) -> List[Path]:
    candidates = list(root.rglob("*.mkv")) if recurse else list(root.glob("*.mkv"))
    candidates = [p for p in candidates if p.is_file()]
    rename_files(candidates)

    refresh = list(root.rglob("*.mkv")) if recurse else list(root.glob("*.mkv"))
    files_to_process: List[Path] = []
    for file_path in refresh:
        if not file_path.is_file():
            continue
        if file_path.name.lower().endswith("_hevc.mkv"):
            continue
        output = file_path.with_name(f"{file_path.stem}_HEVC.mkv")
        if output.exists():
            continue
        files_to_process.append(file_path)
    return files_to_process


def run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def stream_count(path: Path, selector: str) -> int:
    proc = run([
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        selector,
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ])
    if proc.returncode != 0 or not proc.stdout.strip():
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def transcode_file(file_path: Path, index: int, total: int, video_codec: str, preset: str, quality_opts: Sequence[str]) -> None:
    global FAILED_COUNT, TEMP_OUTPUT

    output = file_path.with_name(f"{file_path.stem}_HEVC.mkv")
    temp_output = file_path.with_name(f"{file_path.stem}_HEVC.tmp.mkv")
    TEMP_OUTPUT = temp_output

    if temp_output.exists():
        temp_output.unlink()

    print(f"\n\nProcessing file {index} of {total}\n")
    print(f"Transcoding '{file_path}' using {video_codec}...")

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-i",
        str(file_path),
        "-map",
        "0:v:0?",
        "-map",
        "0:a?",
        "-map",
        "0:s?",
        "-c:v",
        video_codec,
        *quality_opts,
        "-preset",
        preset,
        "-c:a",
        "copy",
        "-c:s",
        "copy",
        "-map_metadata",
        "-1",
        "-y",
        str(temp_output),
    ]

    result = subprocess.run(ffmpeg_cmd, check=False)
    print()

    if result.returncode != 0:
        print(f"Error: ffmpeg failed on '{file_path}'. Keeping source.", file=sys.stderr)
        if temp_output.exists():
            temp_output.unlink()
        FAILED_COUNT += 1
        TEMP_OUTPUT = None
        return

    if not temp_output.exists() or temp_output.stat().st_size == 0:
        print(f"Error: Temporary output '{temp_output}' is empty. Keeping source.", file=sys.stderr)
        if temp_output.exists():
            temp_output.unlink()
        FAILED_COUNT += 1
        TEMP_OUTPUT = None
        return

    verify = run(["ffprobe", "-v", "error", str(temp_output)])
    if verify.returncode != 0:
        print(f"Error: Output verification failed for '{file_path}'. Keeping source.", file=sys.stderr)
        temp_output.unlink(missing_ok=True)
        FAILED_COUNT += 1
        TEMP_OUTPUT = None
        return

    in_audio = stream_count(file_path, "a")
    out_audio = stream_count(temp_output, "a")
    if in_audio > 0 and out_audio < in_audio:
        print(
            f"Error: Audio stream count mismatch for '{file_path}' ({in_audio} input, {out_audio} output). Keeping source.",
            file=sys.stderr,
        )
        temp_output.unlink(missing_ok=True)
        FAILED_COUNT += 1
        TEMP_OUTPUT = None
        return

    shutil.move(str(temp_output), str(output))
    file_path.unlink()
    print(f"Successfully transcoded '{file_path}' to '{output}'. Source deleted.")
    TEMP_OUTPUT = None


def cleanup_and_exit(*_: object) -> None:
    if TEMP_OUTPUT and TEMP_OUTPUT.exists():
        TEMP_OUTPUT.unlink(missing_ok=True)
    sys.exit(1)


def main() -> int:
    args = parse_args()
    video_codec, preset, quality_opts = resolve_encoder(args)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, cleanup_and_exit)

    files = collect_files(Path.cwd(), args.recurse)
    if not files:
        print("No eligible MKV files found to process.")
        return 0

    total = len(files)
    for idx, file_path in enumerate(files, start=1):
        transcode_file(file_path, idx, total, video_codec, preset, quality_opts)

    return 1 if FAILED_COUNT > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
