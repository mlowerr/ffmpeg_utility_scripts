#!/usr/bin/env python3
import argparse
import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from functools import lru_cache
from pathlib import Path

PROFILES = {
    "h264_mp4": {"ext": ".mp4", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_avi": {"ext": ".avi", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_mov": {"ext": ".mov", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_m4v": {"ext": ".m4v", "suffix": "_REDU", "out_ext": ".m4v", "mode": "video", "quality": 26},
    "h264_mpg": {"ext": ".mpg", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_mpeg": {"ext": ".mpeg", "suffix": "_REDU", "out_ext": ".mpeg", "mode": "video", "quality": 26},
    "h264_flv": {"ext": ".flv", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "h264_wmv": {"ext": ".wmv", "suffix": "_REDU", "out_ext": ".mp4", "mode": "video", "quality": 24},
    "h264_rm": {"ext": ".rm", "suffix": "_REDU", "out_ext": ".mpg", "mode": "video", "quality": 26},
    "h264_rmvb": {"ext": ".rmvb", "suffix": "_REDU", "out_ext": ".mpg", "mode": "video", "quality": 26},
    "hevc_mp4": {"ext": ".mp4", "suffix": "_HEVC_REDU", "out_ext": ".mp4", "mode": "video", "quality": 26},
    "hevc_mkv": {"ext": ".mkv", "suffix": "_HEVC_REDU", "out_ext": ".mkv", "mode": "video", "quality": 26},
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


def run_capture(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


@lru_cache(maxsize=1)
def ffmpeg_filter_names():
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    if probe.returncode != 0:
        return set()
    filters = set()
    for line in probe.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            filters.add(parts[1])
    return filters


def cuda_scale_filter(cuda_decode=False):
    filters = ffmpeg_filter_names()
    upload_prefix = "" if cuda_decode else "format=nv12,hwupload_cuda,"
    if "scale_cuda" in filters:
        return f"{upload_prefix}scale_cuda=w='min(1920,iw)':h=-2:format=nv12"
    if "scale_npp" in filters:
        return f"{upload_prefix}scale_npp=w='min(1920,iw)':h=-2:format=nv12"
    return None


def run_ffmpeg(cmd):
    stderr_chunks = []
    recent_lines = deque(maxlen=5)
    rendered_lines = 0
    use_compact_view = sys.stderr.isatty()

    def render_recent_lines():
        nonlocal rendered_lines
        if not use_compact_view:
            return
        if rendered_lines:
            sys.stderr.write(f"\x1b[{rendered_lines}F")
        for line in recent_lines:
            sys.stderr.write("\x1b[2K" + line + "\n")
        rendered_lines = len(recent_lines)
        sys.stderr.flush()

    with subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1) as proc:
        assert proc.stderr is not None
        for chunk in proc.stderr:
            stderr_chunks.append(chunk)
            for line in chunk.splitlines():
                recent_lines.append(line)
                if use_compact_view:
                    render_recent_lines()
                else:
                    sys.stderr.write(line + "\n")
                    sys.stderr.flush()
        returncode = proc.wait()

    if use_compact_view and rendered_lines:
        sys.stderr.write("\x1b[2K")
        sys.stderr.flush()
    return returncode, "".join(stderr_chunks)


def run_ffmpeg_with_progress(cmd, file_index, total_files, source_path):
    print(f"Working on [File {file_index} of {total_files}] [{source_path.resolve()}]")
    return run_ffmpeg(cmd)


def is_audio_copy_compat_failure(stderr: str):
    normalized = stderr.lower()
    signatures = (
        "could not find tag for codec",
        "codec not currently supported in container",
        "unsupported codec",
        "invalid argument",
    )
    return any(sig in normalized for sig in signatures)


def ffmpeg_error_context(stderr_text: str, src: Path):
    detail = (stderr_text or "").strip()
    if not detail:
        detail = "No stderr output from ffmpeg."
    return f"Error: ffmpeg failed on {src}\n{detail}"


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


def build_video_cmd(src, tmp, profile, hw, threads, quality_override=None, force_aac=False, cuda_decode=False):
    q = quality_override if quality_override is not None else profile["quality"]
    scale_opts = []
    cuda_filter = None
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
            cuda_filter = cuda_scale_filter(cuda_decode=cuda_decode) if hw == "nvenc" else None
            if cuda_filter:
                scale_opts = ["-vf", cuda_filter]
            else:
                codec = "libx264"
                preset = "veryfast"
                qopts = ["-crf", "22"]
                scale_opts = ["-vf", "scale='min(1920,iw)':-2"]

    input_opts = []
    # Preserve CUDA-resident frames when the UHD NVENC path can keep decode, scale,
    # and encode on the GPU. For other paths, request CUDA decode without forcing
    # CUDA output frames because CPU-side filters may need system-memory frames.
    if hw == "nvenc" and cuda_decode and codec.endswith("_nvenc"):
        input_opts = ["-hwaccel", "cuda"]
        if scale_opts and cuda_filter:
            input_opts += ["-hwaccel_output_format", "cuda"]

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        *input_opts,
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
    return run_capture(["ffprobe", "-v", "error", str(path)]).returncode == 0


def count_audio(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if p.returncode != 0:
        return 0
    return len([x for x in p.stdout.splitlines() if x.strip()])


def existing_tmp_is_stable(path: Path, delay: float = 1.0):
    try:
        before = path.stat()
    except FileNotFoundError:
        return False
    time.sleep(delay)
    try:
        after = path.stat()
    except FileNotFoundError:
        return False
    return before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns


HARDLINK_UNSUPPORTED_ERRNOS = {
    errno.EACCES,
    errno.EPERM,
    errno.EXDEV,
    errno.EMLINK,
}
for maybe_errno in ("ENOTSUP", "EOPNOTSUPP", "ENOSYS"):
    value = getattr(errno, maybe_errno, None)
    if value is not None:
        HARDLINK_UNSUPPORTED_ERRNOS.add(value)


def copy_output_no_overwrite(tmp: Path, out: Path):
    """Copy tmp to out using exclusive creation so an existing output is kept."""
    out_fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(out_fd, "wb") as out_file:
            out_fd = -1
            with tmp.open("rb") as src_file:
                shutil.copyfileobj(src_file, out_file, length=16 * 1024 * 1024)
            out_file.flush()
            os.fsync(out_file.fileno())
    except BaseException:
        if out_fd >= 0:
            os.close(out_fd)
        out.unlink(missing_ok=True)
        raise

    try:
        tmp.unlink()
    except OSError:
        return False
    return True


def finalize_output_no_overwrite(tmp: Path, out: Path):
    """Finalize tmp as out without ever replacing an existing destination.

    POSIX first uses a hard link, which is atomic and fails if the output
    already exists. If the filesystem does not support hard links, fall back to
    an exclusive-create copy so exFAT/FAT and network mounts still complete
    without overwriting an existing output. On Windows, os.rename provides
    same-directory no-overwrite behavior.

    Returns True when the temporary path was removed or moved away; False means
    the output was finalized but the temporary hard-link cleanup failed.
    """
    try:
        if os.name == "nt":
            os.rename(tmp, out)
            return True
        os.link(tmp, out)
    except FileExistsError:
        raise
    except OSError as exc:
        if out.exists():
            raise FileExistsError(f"destination already exists: {out}") from exc
        if exc.errno in HARDLINK_UNSUPPORTED_ERRNOS:
            return copy_output_no_overwrite(tmp, out)
        raise

    try:
        tmp.unlink()
    except OSError:
        return False
    return True

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
    ap.add_argument("-r", "--recurse", dest="recurse", action="store_true")
    ap.add_argument("--hw", choices=["software", "qsv", "nvenc", "amf", "auto"], default="software")
    ap.add_argument("--threads", type=int)
    ap.add_argument("--skip-dir", action="append", default=[])
    ap.add_argument("--quality", type=int)
    ap.add_argument("--config")
    ap.add_argument(
        "-c",
        "--cuda-decode",
        action="store_true",
        help="When using --hw nvenc, request CUDA hardware decode input options before -i; falls back to CPU decode on failure",
    )
    ap.add_argument("--strict-cleanup", action="store_true", help="Treat source cleanup issues as hard failures")
    args = ap.parse_args()
    if args.hw == "auto":
        args.hw = "software"
    if args.cuda_decode and args.hw != "nvenc":
        print("Warning: --cuda-decode only applies with --hw nvenc; using CPU decode.", file=sys.stderr)
        args.cuda_decode = False

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
        if args.profile == "h264_mpg" and p.name.lower().endswith("_redu.mpg"):
            # Avoid reprocessing RM/RMVB outputs (and other already reduced MPG names)
            # into *_REDU_REDU.mp4 on subsequent runs.
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

    transcode_failures = 0
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
            src, _ = normalize_input_name(original_src)
            out, tmp = out_name(src, profile)
            if out.exists():
                msg = f"Skipping {src}: converted output already exists at {out} (possible duplicate after normalization)."
                print(msg, file=sys.stderr)
                duplicate_skips.append(msg)
                continue
            if tmp.exists():
                if not existing_tmp_is_stable(tmp):
                    print(f"Skipping {src}: temporary output is still changing at {tmp}.", file=sys.stderr)
                    duplicate_skips.append(f"Skipping {src}: temporary output is still changing at {tmp}.")
                    continue
                print(f"Removing stale temporary output before retrying: {tmp}", file=sys.stderr)
                tmp.unlink(missing_ok=True)
            active_tmp = tmp
            cuda_decode_active = profile["mode"] == "video" and args.hw == "nvenc" and args.cuda_decode
            cmd = (
                build_audio_cmd(src, tmp)
                if profile["mode"] == "audio"
                else build_video_cmd(
                    src,
                    tmp,
                    profile,
                    args.hw,
                    args.threads,
                    quality_override=selected_quality,
                    cuda_decode=cuda_decode_active,
                )
            )
            returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
            if returncode != 0 and cuda_decode_active:
                print(f"CUDA decode failed for {src}; retrying with CPU decode and NVENC encode.", file=sys.stderr)
                cuda_decode_active = False
                if tmp.exists():
                    tmp.unlink()
                cmd = build_video_cmd(src, tmp, profile, args.hw, args.threads, quality_override=selected_quality)
                returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
            if returncode != 0:
                if profile["mode"] == "video" and profile["ext"] in {".avi", ".flv", ".m4v", ".mov", ".mpg", ".mpeg", ".rm", ".rmvb", ".wmv"}:
                    fallback_reason = "retrying due to incompatible audio copy codec"
                    if not is_audio_copy_compat_failure(stderr_text):
                        print(ffmpeg_error_context(stderr_text, src), file=sys.stderr)
                        transcode_failures += 1
                        if tmp.exists():
                            tmp.unlink()
                        active_tmp = None
                        continue
                    print(f"Audio copy failed for {src}; {fallback_reason}.")
                    if tmp.exists():
                        tmp.unlink()
                    cmd = build_video_cmd(
                        src,
                        tmp,
                        profile,
                        args.hw,
                        args.threads,
                        quality_override=selected_quality,
                        force_aac=True,
                        cuda_decode=cuda_decode_active,
                    )
                    returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
                    if returncode != 0 and cuda_decode_active:
                        print(f"CUDA decode failed for {src}; retrying AAC fallback with CPU decode and NVENC encode.", file=sys.stderr)
                        if tmp.exists():
                            tmp.unlink()
                        cmd = build_video_cmd(
                            src,
                            tmp,
                            profile,
                            args.hw,
                            args.threads,
                            quality_override=selected_quality,
                            force_aac=True,
                        )
                        returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
                    if returncode != 0:
                        print(ffmpeg_error_context(stderr_text, src), file=sys.stderr)
                        transcode_failures += 1
                        if tmp.exists():
                            tmp.unlink()
                        active_tmp = None
                        continue
                else:
                    print(ffmpeg_error_context(stderr_text, src), file=sys.stderr)
                    transcode_failures += 1
                    if tmp.exists():
                        tmp.unlink()
                    active_tmp = None
                    continue
            if not tmp.exists() or tmp.stat().st_size == 0 or not ffprobe_ok(tmp):
                print(f"Error: Output verification failed for {src}", file=sys.stderr)
                transcode_failures += 1
                if tmp.exists():
                    tmp.unlink()
                active_tmp = None
                continue
            if profile["mode"] == "video":
                ina, outa = count_audio(src), count_audio(tmp)
                if ina > 0 and outa < ina:
                    print(f"Error: Audio stream mismatch for {src}", file=sys.stderr)
                    transcode_failures += 1
                    tmp.unlink(missing_ok=True)
                    active_tmp = None
                    continue
            try:
                finalized_tmp_removed = finalize_output_no_overwrite(tmp, out)
            except FileExistsError:
                print(f"Error: Destination already exists for {src}: {out}", file=sys.stderr)
                transcode_failures += 1
                tmp.unlink(missing_ok=True)
                active_tmp = None
                continue
            except Exception as e:
                print(f"Error moving temporary output into place for {src}: {e}", file=sys.stderr)
                transcode_failures += 1
                tmp.unlink(missing_ok=True)
                active_tmp = None
                continue
            if not finalized_tmp_removed:
                print(
                    f"Warning: Output finalized at {out}, but failed to remove temporary hard link {tmp}.",
                    file=sys.stderr,
                )
                cleanup_warnings += 1

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
        transcode_failures += 1
    finally:
        if duplicate_skips:
            print("\nDuplicate-skip summary:", file=sys.stderr)
            for entry in duplicate_skips:
                print(f"- {entry}", file=sys.stderr)
        if cleanup_warnings:
            print(
                f"\nCleanup warning summary: {cleanup_warnings} source cleanup issue(s). Output files were kept.",
                file=sys.stderr,
            )

    hard_failures = transcode_failures + (1 if interrupted else 0)
    if args.strict_cleanup:
        hard_failures += cleanup_warnings

    return 1 if hard_failures > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
