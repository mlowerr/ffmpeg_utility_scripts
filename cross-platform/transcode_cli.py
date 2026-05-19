#!/usr/bin/env python3
import argparse
import signal
import subprocess
import sys
from pathlib import Path

PROFILES = {
    "h264_mp4": {"ext": ".mp4", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_avi": {"ext": ".avi", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_mov": {"ext": ".mov", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_mpg": {"ext": ".mpg", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_flv": {"ext": ".flv", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_wmv": {"ext": ".wmv", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 24},
    "hevc_mp4": {"ext": ".mp4", "suffix": "_HEVC", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "hevc_mkv": {"ext": ".mkv", "suffix": "_HEVC", "out_ext": ".mkv", "mode": "video", "quality": 26},
    "flac_mp3": {"ext": ".flac", "suffix": "", "out_ext": ".mp3", "mode": "audio"},
    "wav_mp3": {"ext": ".wav", "suffix": "", "out_ext": ".mp3", "mode": "audio"},
}


def run(cmd):
    return subprocess.run(cmd).returncode == 0


def out_name(p: Path, profile):
    if profile["mode"] == "audio":
        return p.with_suffix(".mp3"), p.with_suffix(".tmp.mp3")
    stem = p.stem + profile["suffix"]
    return p.with_name(stem + profile["out_ext"]), p.with_name(stem + ".tmp" + profile["out_ext"])


def detect_dimensions(path):
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return None, None
    line = probe.stdout.strip().splitlines()[0] if probe.stdout.strip() else ""
    parts = line.split("x")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def build_video_cmd(src, tmp, profile, hw, threads, force_aac=False):
    q = profile["quality"]
    scale_opts = []
    needs_uhd_fallback = profile["suffix"] == "_REDU" or (profile["suffix"] == "_HEVC" and profile["out_ext"] == ".mp4")

    if profile["suffix"] == "_HEVC":
        codec = "libx265"
        preset = "medium"
        qopts = ["-crf", str(q)]
        if hw == "qsv":
            codec, preset, qopts = "hevc_qsv", "medium", ["-global_quality", str(q)]
        elif hw == "nvenc":
            codec, preset, qopts = "hevc_nvenc", "p4", ["-rc", "vbr", "-cq", str(q)]
        elif hw == "amf":
            codec, preset, qopts = "hevc_amf", "speed", ["-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)]
    else:
        codec = "libx264"
        preset = "veryfast"
        qopts = ["-crf", str(q)]
        if hw == "qsv":
            codec, preset, qopts = "h264_qsv", "fast", ["-global_quality", str(q)]
        elif hw == "nvenc":
            codec, preset, qopts = "h264_nvenc", "p4", ["-rc", "vbr", "-cq", str(q)]
        elif hw == "amf":
            codec, preset, qopts = "h264_amf", "speed", ["-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)]

    if needs_uhd_fallback:
        width, height = detect_dimensions(src)
        if width is not None and height is not None and (width >= 3840 or height >= 2160):
            print(f"UHD/4K detected ({width}x{height}): forcing aspect-safe 1080p downscale profile for stability.")
            codec = "libx264"
            preset = "veryfast"
            qopts = ["-crf", "22"]
            scale_opts = ["-vf", "scale='min(1920,iw)':-2"]

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-i",
        str(src),
        "-map",
        "0:v:0?",
        "-map",
        "0:a?",
    ]
    if profile["out_ext"] == ".mkv":
        cmd += ["-map", "0:s?", "-c:s", "copy"]
    audio_opts = ["-c:a", "copy"]
    if force_aac:
        audio_opts = ["-c:a", "aac", "-b:a", "192k"]
    cmd += scale_opts + ["-c:v", codec, *qopts, "-preset", preset, *audio_opts, "-map_metadata", "-1"]
    if profile["out_ext"] == ".mp4":
        cmd += ["-movflags", "+faststart"]

    if profile["suffix"] == "_HEVC" and codec == "libx265" and threads:
        cmd += ["-x265-params", f"pools={threads}"]

    if threads:
        cmd += ["-threads", str(threads)]
    cmd += ["-y", str(tmp)]
    return cmd


def build_audio_cmd(src, tmp):
    return ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-i", str(src), "-vn", "-map", "0:a:0?", "-c:a", "libmp3lame", "-b:a", "256k", "-map_metadata", "0", "-id3v2_version", "3", "-y", str(tmp)]


def ffprobe_ok(path):
    return run(["ffprobe", "-v", "error", str(path)])


def count_audio(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if p.returncode != 0:
        return 0
    return len([x for x in p.stdout.splitlines() if x.strip()])


def normalize_input_name(path: Path):
    if " " not in path.name:
        return path, False
    normalized = path.with_name(path.name.replace(" ", "_"))
    if normalized.exists():
        print(f"Warning: Cannot rename {path} -> {normalized} (target exists).", file=sys.stderr)
        return path, False
    try:
        path.replace(normalized)
        print(f"Renamed {path} -> {normalized}")
        return normalized, True
    except OSError as exc:
        print(f"Warning: Failed to rename {path} -> {normalized}: {exc}", file=sys.stderr)
        return path, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, choices=sorted(PROFILES))
    ap.add_argument("--path", default=".")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--hw", choices=["software", "qsv", "nvenc", "amf", "auto"], default="software")
    ap.add_argument("--threads", type=int)
    args = ap.parse_args()
    if args.hw == "auto":
        args.hw = "software"

    profile = PROFILES[args.profile]
    root = Path(args.path)
    files = root.rglob("*") if args.recursive else root.glob("*")
    candidates = []
    for p in files:
        if not p.is_file():
            continue
        if p.suffix.lower() != profile["ext"]:
            continue
        out, _ = out_name(p, profile)
        if profile["suffix"] and p.name.lower().endswith((profile["suffix"] + profile["out_ext"]).lower()):
            continue
        if out.exists():
            continue
        candidates.append(p)
    candidates = sorted(candidates, key=lambda item: str(item).lower())

    if not candidates:
        print(f"No eligible {profile['ext']} files found to process.")
        return 0

    failed = 0
    active_tmp = None
    interrupted = False

    def cleanup_and_exit(signum, _frame):
        nonlocal active_tmp, interrupted
        interrupted = True
        if active_tmp and active_tmp.exists():
            active_tmp.unlink(missing_ok=True)
        raise KeyboardInterrupt(f"Signal {signum}")

    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    try:
        for i, original_src in enumerate(candidates, 1):
            print(f"\n\nProcessing file {i} of {len(candidates)}\n")
            src, _ = normalize_input_name(original_src)
            out, tmp = out_name(src, profile)
            active_tmp = tmp
            if tmp.exists():
                tmp.unlink()
            cmd = build_audio_cmd(src, tmp) if profile["mode"] == "audio" else build_video_cmd(src, tmp, profile, args.hw, args.threads)
            if not run(cmd):
                if profile["mode"] == "video" and profile["ext"] in {".avi", ".flv", ".mov", ".mpg", ".wmv"}:
                    print(f"Audio copy failed for {src}; retrying with AAC audio fallback.")
                    if tmp.exists():
                        tmp.unlink()
                    cmd = build_video_cmd(src, tmp, profile, args.hw, args.threads, force_aac=True)
                    if not run(cmd):
                        print(f"Error: ffmpeg failed on {src}", file=sys.stderr)
                        failed += 1
                        if tmp.exists():
                            tmp.unlink()
                        active_tmp = None
                        continue
                else:
                    print(f"Error: ffmpeg failed on {src}", file=sys.stderr)
                    failed += 1
                    if tmp.exists():
                        tmp.unlink()
                    active_tmp = None
                    continue
            if not tmp.exists() or tmp.stat().st_size == 0 or not ffprobe_ok(tmp):
                print(f"Error: Output verification failed for {src}", file=sys.stderr)
                failed += 1
                if tmp.exists():
                    tmp.unlink()
                active_tmp = None
                continue
            if profile["mode"] == "video":
                ina, outa = count_audio(src), count_audio(tmp)
                if ina > 0 and outa < ina:
                    print(f"Error: Audio stream mismatch for {src}", file=sys.stderr)
                    failed += 1
                    tmp.unlink(missing_ok=True)
                    active_tmp = None
                    continue
            try:
                tmp.replace(out)
                src.unlink()
                print(f"Successfully processed {src} -> {out}")
            except Exception as e:
                print(f"Error finalizing {src}: {e}", file=sys.stderr)
                failed += 1
                tmp.unlink(missing_ok=True)
            active_tmp = None
    except KeyboardInterrupt:
        print("\nInterrupted. Cleaned up active temporary output file.", file=sys.stderr)
        failed += 1

    return 1 if failed or interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
