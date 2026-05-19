#!/usr/bin/env python3
import argparse
import os
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


def build_video_cmd(src, tmp, profile, hw, threads):
    q = profile["quality"]
    if profile["suffix"] == "_HEVC":
        codec = "libx265"; preset = "medium"; qopts = ["-crf", str(q)]
        if hw == "qsv": codec, preset, qopts = "hevc_qsv", "medium", ["-global_quality", str(q)]
        elif hw == "nvenc": codec, preset, qopts = "hevc_nvenc", "p4", ["-rc", "vbr", "-cq", str(q)]
        elif hw == "amf": codec, preset, qopts = "hevc_amf", "speed", ["-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)]
    else:
        codec = "libx264"; preset = "veryfast"; qopts = ["-crf", str(q)]
        if hw == "qsv": codec, preset, qopts = "h264_qsv", "fast", ["-global_quality", str(q)]
        elif hw == "nvenc": codec, preset, qopts = "h264_nvenc", "p4", ["-rc", "vbr", "-cq", str(q)]
        elif hw == "amf": codec, preset, qopts = "h264_amf", "speed", ["-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)]

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-i", str(src), "-map", "0:v:0?", "-map", "0:a?",
           "-c:v", codec, *qopts, "-preset", preset, "-c:a", "copy", "-map_metadata", "-1"]
    if profile["out_ext"] == ".mp4":
        cmd += ["-movflags", "+faststart"]
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

    if not candidates:
        print(f"No eligible {profile['ext']} files found to process.")
        return 0

    failed = 0
    for i, src in enumerate(candidates, 1):
        print(f"\n\nProcessing file {i} of {len(candidates)}\n")
        out, tmp = out_name(src, profile)
        if tmp.exists():
            tmp.unlink()
        cmd = build_audio_cmd(src, tmp) if profile["mode"] == "audio" else build_video_cmd(src, tmp, profile, args.hw, args.threads)
        if not run(cmd):
            print(f"Error: ffmpeg failed on {src}", file=sys.stderr); failed += 1
            if tmp.exists(): tmp.unlink()
            continue
        if not tmp.exists() or tmp.stat().st_size == 0 or not ffprobe_ok(tmp):
            print(f"Error: Output verification failed for {src}", file=sys.stderr); failed += 1
            if tmp.exists(): tmp.unlink()
            continue
        if profile["mode"] == "video":
            ina, outa = count_audio(src), count_audio(tmp)
            if ina > 0 and outa < ina:
                print(f"Error: Audio stream mismatch for {src}", file=sys.stderr); failed += 1
                tmp.unlink(missing_ok=True)
                continue
        try:
            tmp.replace(out)
            src.unlink()
            print(f"Successfully processed {src} -> {out}")
        except Exception as e:
            print(f"Error finalizing {src}: {e}", file=sys.stderr); failed += 1
            tmp.unlink(missing_ok=True)

    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
