#!/usr/bin/env python3
"""FFmpeg/FFprobe command construction, execution, probing, and diagnostics."""
import json
import subprocess
import sys
from collections import deque
from fractions import Fraction
from functools import lru_cache
from pathlib import Path


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
    if "unsupported audio codec" in normalized:
        return True
    signatures = (
        "could not find tag for codec",
        "codec not currently supported in container",
        "unsupported codec",
    )
    if not any(sig in normalized for sig in signatures):
        return False
    if any(codec in normalized for codec in ("codec h264", "codec hevc", "codec av1", "codec vp8", "codec vp9")):
        return False
    return True


def ffmpeg_error_context(stderr_text: str, src: Path):
    detail = (stderr_text or "").strip()
    if not detail:
        detail = "No stderr output from ffmpeg."
    return f"Error: ffmpeg failed on {src}\n{detail}"


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


def wmv_needs_timing_normalization(path):
    """Detect WMV frame rates that exceed practical H.264/MP4 limits."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate,r_frame_rate,time_base",
             "-of", "json", str(path)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    if probe.returncode != 0:
        return False
    try:
        stream = json.loads(probe.stdout).get("streams", [])[0]
    except (AttributeError, IndexError, json.JSONDecodeError):
        return False
    rates = []
    for name in ("avg_frame_rate", "r_frame_rate"):
        try:
            rate = float(Fraction(stream.get(name, "0/0")))
        except (ValueError, ZeroDivisionError):
            rate = 0
        if rate > 0:
            rates.append(rate)
    return bool(rates) and max(rates) > 240


def fallback_audio_layout_options(audio_streams):
    """Return per-output-stream layouts needed for ambiguous mono inputs."""
    unspecified_layouts = {"", "unknown", "unspecified", "n/a", "none", "1 channel", "1 channels"}
    options = []
    for output_index, stream in enumerate(audio_streams or []):
        layout = stream.get("channel_layout")
        normalized_layout = str(layout or "").strip().lower()
        if stream.get("channels") == 1 and normalized_layout in unspecified_layouts:
            options += [f"-channel_layout:a:{output_index}", "mono"]
    return options


def build_video_cmd(src, tmp, profile, hw, threads, quality_override=None, force_audio_fallback=False,
                    cuda_decode=False, audio_streams=None):
    q = quality_override if quality_override is not None else profile["quality"]
    scale_opts = []
    cuda_filter = None
    is_hevc = profile.get("video_codec_family") == "hevc" or profile["suffix"].startswith("_HEVC")
    needs_uhd_fallback = profile["suffix"] == "_REDU" or (
        profile["suffix"].startswith("_HEVC") and profile["out_ext"] == ".mp4"
    )

    if is_hevc:
        codec = "libx265"
        preset = profile.get("preset", "medium")
        qopts = ["-crf", str(q)]
        if hw == "qsv":
            codec, preset, qopts = "hevc_qsv", "medium", ["-global_quality", str(q)]
        elif hw == "nvenc":
            codec, preset, qopts = "hevc_nvenc", "p4", ["-rc", "vbr", "-cq", str(q)]
        elif hw == "amf":
            codec, preset, qopts = "hevc_amf", "speed", ["-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)]
    else:
        codec = "libx264"
        preset = profile.get("preset", "veryfast")
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
    audio_opts = ["-c:a", profile.get("audio_codec", "copy")]
    if profile.get("audio_bitrate"):
        audio_opts += ["-b:a", profile["audio_bitrate"]]
    if force_audio_fallback:
        fallback_codec = "mp2" if profile["out_ext"] in {".mpg", ".mpeg"} else "aac"
        audio_opts = ["-c:a", fallback_codec, "-b:a", "192k"]
        if fallback_codec == "aac":
            audio_opts += fallback_audio_layout_options(audio_streams)
    if profile.get("video_filter"):
        scale_opts = ["-vf", profile["video_filter"]]
    cmd += scale_opts + ["-c:v", codec, *qopts, "-preset", preset, *audio_opts, "-map_metadata", "-1"]
    if profile["out_ext"] == ".mp4":
        cmd += ["-tag:v", "hvc1" if is_hevc else "avc1", "-movflags", "+faststart"]
    if profile["ext"] == ".wmv" and wmv_needs_timing_normalization(src):
        cmd += ["-fps_mode", "cfr", "-r", "30"]

    if is_hevc and codec == "libx265" and threads:
        cmd += ["-x265-params", f"pools={threads}"]

    if threads:
        cmd += ["-threads", str(threads)]
    cmd += ["-y", str(tmp)]
    return cmd


def build_audio_cmd(src, tmp):
    return ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-i", str(src), "-vn", "-map", "0:a:0?", "-c:a", "libmp3lame", "-b:a", "256k", "-map_metadata", "0", "-id3v2_version", "3", "-y", str(tmp)]


def ffprobe_ok(path):
    return run_capture(["ffprobe", "-v", "error", str(path)]).returncode == 0


def probe_audio_streams(path):
    """Return audio stream details, preserving ffprobe failures for diagnostics."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index,codec_name,channels,channel_layout:stream_disposition:stream_tags=language,title",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or "No stderr output from ffprobe."
        raise RuntimeError(f"ffprobe failed for {path}: {detail}")
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except (AttributeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ffprobe returned invalid audio stream data for {path}: {exc}") from exc
    if not isinstance(streams, list):
        raise RuntimeError(f"ffprobe returned invalid audio stream data for {path}: streams is not a list")
    return streams


def format_audio_streams(streams):
    if not streams:
        return "none"
    return "; ".join(
        f"index={stream.get('index', '?')}, codec={stream.get('codec_name', 'unknown')}, "
        f"channels={stream.get('channels', 'unknown')}, "
        f"channel_layout={stream.get('channel_layout', 'unknown')}, "
        f"language={stream.get('tags', {}).get('language', 'unknown')}, "
        f"title={stream.get('tags', {}).get('title', 'none')}, "
        f"default={stream.get('disposition', {}).get('default', 0)}"
        for stream in streams
    )


def probe_media(path: Path):
    """Return the duration and stream inventory used for checkpoint validation."""
    proc = run_capture([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", str(path),
    ])
    if proc.returncode != 0:
        raise ValueError(f"ffprobe could not parse {path}")
    try:
        data = json.loads(proc.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        streams = [item.get("codec_type") for item in data.get("streams", [])]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid ffprobe response for {path}: {exc}") from exc
    return {"duration": duration, "video": streams.count("video"),
            "audio": streams.count("audio"), "subtitle": streams.count("subtitle")}