#!/usr/bin/env python3
import argparse
import json
import os
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


def default_config_path():
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "ffmpeg-utility-scripts" / "config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ffmpeg-utility-scripts" / "config.json"


def load_user_config(config_path: Path, required: bool = False):
    if not config_path.exists():
        if required:
            raise ValueError(f"config file does not exist: {config_path}")
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to parse config file {config_path}: {exc}")
    if not isinstance(data, dict):
        raise ValueError("config file must contain a JSON object")
    return data


def normalize_skip_dirs(skip_dir_values, root: Path):
    normalized = []
    seen = set()
    for raw in skip_dir_values:
        try:
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = (root / candidate).resolve()
            else:
                candidate = candidate.resolve()
        except Exception:
            continue
        key = str(candidate)
        if key not in seen:
            normalized.append(candidate)
            seen.add(key)
    return normalized


def is_path_under(parent: Path, child: Path):
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def should_skip_file(file_path: Path, skip_dirs):
    return any(is_path_under(skip_dir, file_path) for skip_dir in skip_dirs)


def validate_quality_value(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if not (0 <= value <= 51):
        raise ValueError(f"{label} must be between 0 and 51")


def effective_quality(profile_name: str, profile: dict, config: dict, cli_quality):
    if profile["mode"] != "video":
        return None
    if cli_quality is not None:
        return cli_quality
    qcfg = config.get("quality", {})
    if isinstance(qcfg, dict):
        if profile_name in qcfg:
            validate_quality_value(qcfg[profile_name], f"config quality.{profile_name}")
            return qcfg[profile_name]
        if "default_video" in qcfg:
            validate_quality_value(qcfg["default_video"], "config quality.default_video")
            return qcfg["default_video"]
    elif qcfg != {}:
        validate_quality_value(qcfg, "config quality")
        return qcfg
    return profile["quality"]


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


def build_video_cmd(src, tmp, profile, hw, threads, quality_override=None, force_aac=False):
    q = quality_override if quality_override is not None else profile["quality"]
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
        return path, False, False
    normalized = path.with_name(path.name.replace(" ", "_"))
    if normalized.exists():
        print(f"Warning: Cannot rename {path} -> {normalized} (target exists).", file=sys.stderr)
        return path, False, True
    try:
        path.replace(normalized)
        print(f"Renamed {path} -> {normalized}")
        return normalized, True, False
    except OSError as exc:
        print(f"Warning: Failed to rename {path} -> {normalized}: {exc}", file=sys.stderr)
        return path, False, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, choices=sorted(PROFILES))
    ap.add_argument("--path", default=".")
    ap.add_argument("-r", "--recurse", dest="recurse", action="store_true")
    ap.add_argument("--hw", choices=["software", "qsv", "nvenc", "amf", "auto"], default="software")
    ap.add_argument("--threads", type=int)
    ap.add_argument("--skip-dir", action="append", default=[])
    ap.add_argument("--quality", type=int)
    ap.add_argument("--config")
    ap.add_argument("--strict-cleanup", action="store_true")
    args = ap.parse_args()
    if args.hw == "auto":
        args.hw = "software"

    profile = PROFILES[args.profile]
    if args.threads is not None and args.threads < 0:
        print("Error: --threads must be zero or a positive integer", file=sys.stderr)
        return 1
    if args.quality is not None and not (0 <= args.quality <= 51):
        print("Error: --quality must be between 0 and 51", file=sys.stderr)
        return 1

    try:
        root = Path(args.path).expanduser().resolve()
    except Exception as exc:
        print(f"Error: unable to resolve target path '{args.path}': {exc}", file=sys.stderr)
        return 1

    if not root.exists():
        print(f"Error: target path does not exist: {root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"Error: target path is not a directory: {root}", file=sys.stderr)
        return 1

    config_path = Path(args.config).expanduser().resolve() if args.config else default_config_path()
    try:
        config = load_user_config(config_path, required=bool(args.config))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    config_skip_dirs = config.get("skip_dirs", [])
    if not isinstance(config_skip_dirs, list):
        print("Error: config key 'skip_dirs' must be a list", file=sys.stderr)
        return 1
    raw_skip_dirs = [*config_skip_dirs, *args.skip_dir]
    skip_dirs = normalize_skip_dirs(raw_skip_dirs, root)
    try:
        selected_quality = effective_quality(args.profile, profile, config, args.quality)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    files = root.rglob("*") if args.recurse else root.glob("*")
    candidates = []
    for p in files:
        if not p.is_file():
            continue
        if p.suffix.lower() != profile["ext"]:
            continue
        if should_skip_file(p.resolve(), skip_dirs):
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

    hard_failures = 0
    cleanup_warnings = 0
    duplicate_skips = []
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
            src, _, rename_warning = normalize_input_name(original_src)
            if rename_warning:
                cleanup_warnings += 1
            out, tmp = out_name(src, profile)
            if out.exists():
                msg = f"Skipping {src}: converted output already exists at {out} (possible duplicate after normalization)."
                print(msg, file=sys.stderr)
                duplicate_skips.append(msg)
                continue
            active_tmp = tmp
            if tmp.exists():
                tmp.unlink()
            cmd = build_audio_cmd(src, tmp) if profile["mode"] == "audio" else build_video_cmd(src, tmp, profile, args.hw, args.threads, quality_override=selected_quality)
            if not run(cmd):
                if profile["mode"] == "video" and profile["ext"] in {".avi", ".flv", ".mov", ".mpg", ".wmv"}:
                    print(f"Audio copy failed for {src}; retrying with AAC audio fallback.")
                    if tmp.exists():
                        tmp.unlink()
                    cmd = build_video_cmd(src, tmp, profile, args.hw, args.threads, quality_override=selected_quality, force_aac=True)
                    if not run(cmd):
                        print(f"Error: ffmpeg failed on {src}", file=sys.stderr)
                        hard_failures += 1
                        if tmp.exists():
                            tmp.unlink()
                        active_tmp = None
                        continue
                else:
                    print(f"Error: ffmpeg failed on {src}", file=sys.stderr)
                    hard_failures += 1
                    if tmp.exists():
                        tmp.unlink()
                    active_tmp = None
                    continue
            if not tmp.exists() or tmp.stat().st_size == 0 or not ffprobe_ok(tmp):
                print(f"Error: Output verification failed for {src}", file=sys.stderr)
                hard_failures += 1
                if tmp.exists():
                    tmp.unlink()
                active_tmp = None
                continue
            if profile["mode"] == "video":
                ina, outa = count_audio(src), count_audio(tmp)
                if ina > 0 and outa < ina:
                    print(f"Error: Audio stream mismatch for {src}", file=sys.stderr)
                    hard_failures += 1
                    tmp.unlink(missing_ok=True)
                    active_tmp = None
                    continue
            try:
                tmp.replace(out)
            except Exception as e:
                print(f"Error moving temporary output into place for {src}: {e}", file=sys.stderr)
                hard_failures += 1
                tmp.unlink(missing_ok=True)
                active_tmp = None
                continue

            try:
                src.unlink()
                print(f"Successfully processed {src} -> {out}")
            except Exception as e:
                print(
                    f"Error deleting source after successful output finalize for {src}: {e}. Output kept at {out}.",
                    file=sys.stderr,
                )
                cleanup_warnings += 1
            active_tmp = None
    except KeyboardInterrupt:
        print("\nInterrupted. Cleaned up active temporary output file.", file=sys.stderr)
        hard_failures += 1
    finally:
        if duplicate_skips:
            print("\nDuplicate-skip summary:", file=sys.stderr)
            for entry in duplicate_skips:
                print(f"- {entry}", file=sys.stderr)

        if cleanup_warnings:
            print(f"\nCleanup warning summary: {cleanup_warnings} source cleanup issue(s).", file=sys.stderr)

    if args.strict_cleanup and cleanup_warnings:
        return 1

    return 1 if hard_failures or interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
