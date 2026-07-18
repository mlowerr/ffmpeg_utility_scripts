#!/usr/bin/env python3
import argparse
import hashlib
import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections import deque
from functools import lru_cache
from pathlib import Path

ZERO_BYTE_TMP_CLAIM_STALE_SECONDS = 45 * 60
CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_LOCK_STALE_SECONDS = 48 * 60 * 60
CHECKPOINT_DURATION_TOLERANCE_SECONDS = 0.5

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
    "hevc_mkv_legacy": {"ext": ".mkv", "suffix": "_HEVC", "out_ext": ".mkv", "mode": "video", "quality": 26},
    "mkv_shrink": {"ext": ".mkv", "suffix": "_small", "out_ext": ".mp4", "mode": "video", "quality": 28,
                   "video_filter": "scale=-2:1080,fps=30", "audio_codec": "aac", "audio_bitrate": "96k",
                   "preserve_source": True, "video_codec_family": "hevc", "preset": "veryfast"},
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


def is_temporary_transcode_path(path: Path):
    return ".tmp." in path.name.lower()


def is_checkpoint_internal_path(path: Path):
    """Return true for files retained inside checkpoint or quarantine trees."""
    return any(".transcode-checkpoint-" in part for part in path.parts)


def discover_paths(root: Path, recurse: bool):
    """Discover files while pruning checkpoint and quarantine directory trees."""
    if not recurse:
        yield from root.glob("*")
        return
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if ".transcode-checkpoint-" not in name]
        parent = Path(directory)
        for name in filenames:
            yield parent / name


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


def build_video_cmd(src, tmp, profile, hw, threads, quality_override=None, force_audio_fallback=False, cuda_decode=False):
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
        fallback_codec = "mp2" if profile["out_ext"] == ".mpeg" else "aac"
        audio_opts = ["-c:a", fallback_codec, "-b:a", "192k"]
    if profile.get("video_filter"):
        scale_opts = ["-vf", profile["video_filter"]]
    cmd += scale_opts + ["-c:v", codec, *qopts, "-preset", preset, *audio_opts, "-map_metadata", "-1"]
    if profile["out_ext"] == ".mp4":
        cmd += ["-movflags", "+faststart"]

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


def count_audio(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if p.returncode != 0:
        return 0
    return len([x for x in p.stdout.splitlines() if x.strip()])


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


def atomic_json_write(path: Path, value):
    pending = path.with_name(path.name + f".{uuid.uuid4().hex}.pending")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, path)


def checkpoint_path(src: Path):
    canonical = str(src.resolve())
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return src.parent / f".{src.name}.transcode-checkpoint-{digest}"


def process_identity():
    """PID plus boot/process-start identities prevent PID-reuse-only lock decisions."""
    boot = "unknown"
    started = "unknown"
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        started = Path(f"/proc/{os.getpid()}/stat").read_text(encoding="ascii").split()[21]
    except (OSError, IndexError):
        started = str(time.time_ns())
    return {"pid": os.getpid(), "boot_id": boot, "process_start": started,
            "token": uuid.uuid4().hex, "claimed_at": time.time()}


def lock_owner_alive(owner):
    if owner.get("boot_id") == "unknown":
        return False
    try:
        if Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip() != owner["boot_id"]:
            return False
        stat = Path(f"/proc/{int(owner['pid'])}/stat").read_text(encoding="ascii").split()
        return stat[21] == str(owner.get("process_start"))
    except (OSError, ValueError, KeyError, IndexError):
        return False


class CheckpointLock:
    def __init__(self, workdir: Path):
        self.directory = workdir / "lock"
        self.owner = process_identity()

    def acquire(self):
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.directory.mkdir()
        except FileExistsError:
            try:
                current = json.loads((self.directory / "owner.json").read_text(encoding="utf-8"))
                age = time.time() - float(current.get("claimed_at", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                current = {}
                try:
                    age = time.time() - self.directory.stat().st_mtime
                except OSError:
                    age = 0
            # Recovery requires both a dead exact process identity and an expired lease.
            if lock_owner_alive(current) or age < CHECKPOINT_LOCK_STALE_SECONDS:
                raise FileExistsError(f"checkpoint is owned by another invocation: {self.directory}")
            stale = self.directory.with_name(f"lock.stale-{int(time.time())}-{uuid.uuid4().hex[:8]}")
            try:
                os.rename(self.directory, stale)
                shutil.rmtree(stale, ignore_errors=True)
                self.directory.mkdir()
            except OSError as exc:
                raise FileExistsError(f"could not recover checkpoint lock: {exc}") from exc
        atomic_json_write(self.directory / "owner.json", self.owner)

    def release(self):
        try:
            current = json.loads((self.directory / "owner.json").read_text(encoding="utf-8"))
            if current.get("token") == self.owner["token"]:
                shutil.rmtree(self.directory)
        except (OSError, json.JSONDecodeError):
            pass


def checkpoint_signature(src, profile_name, profile, hw, threads, quality, segment_duration, command):
    stat = src.stat()
    codec = command[command.index("-c:v") + 1]
    def option_values(flag):
        return [command[i + 1] for i, item in enumerate(command[:-1]) if item == flag]
    filters = option_values("-vf") + ["setpts=PTS-STARTPTS"]
    if "-c:a" in command and command[command.index("-c:a") + 1] != "copy":
        filters.append("asetpts=PTS-STARTPTS")
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "source_path": str(src.resolve()), "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns, "profile": profile_name,
        "output_extension": profile["out_ext"], "codec": codec, "hardware_backend": hw,
        "quality": quality, "threads": threads or 0,
        "filters": filters,
        "stream_mappings": option_values("-map"), "segment_duration": segment_duration,
        "command_options": command[1:-2],
    }


def validate_segment(path, expected, expected_duration=None):
    try:
        actual = probe_media(path)
    except ValueError:
        return False
    duration_ok = True
    if expected_duration is not None:
        tolerance = min(CHECKPOINT_DURATION_TOLERANCE_SECONDS, max(0.10, expected_duration * 0.002))
        duration_ok = abs(actual["duration"] - expected_duration) <= tolerance
    return path.is_file() and path.stat().st_size > 0 and duration_ok and actual["video"] >= 1 \
        and actual["audio"] == expected["audio"] \
        and actual["subtitle"] == expected["subtitle"]


def manifest_segment_path(workdir: Path, entry, position: int):
    """Return a checked checkpoint segment path for a manifest entry."""
    if not isinstance(entry, dict):
        raise ValueError("manifest segment entry is corrupt")
    expected_name = f"segment-{position:08d}.mkv"
    filename = entry.get("file")
    if entry.get("index") != position or filename != expected_name:
        raise ValueError(f"manifest segment entry does not match expected segment {position}")
    if Path(filename).name != filename:
        raise ValueError(f"manifest segment path escapes checkpoint directory: {filename}")
    segment = (workdir / filename).resolve()
    root = workdir.resolve()
    if segment.parent != root:
        raise ValueError(f"manifest segment path escapes checkpoint directory: {filename}")
    return segment


def validate_completed_segments(workdir, manifest, expected, manifest_path):
    """Validate retained segments, allowing only an invalid final entry to be retried."""
    completed = manifest.get("completed")
    if not isinstance(completed, list):
        raise ValueError("manifest completed list is corrupt")
    for position, entry in enumerate(list(completed)):
        segment = manifest_segment_path(workdir, entry, position)
        if not validate_segment(segment, expected, entry.get("source_duration")):
            if position != len(completed) - 1:
                raise ValueError(f"non-trailing checkpoint segment is invalid: {segment}")
            segment.unlink(missing_ok=True)
            completed.pop()
            atomic_json_write(manifest_path, manifest)
    return completed


def quarantine_checkpoint(workdir: Path, reason: str):
    target = workdir.with_name(f"{workdir.name}.quarantine-{int(time.time())}-{uuid.uuid4().hex[:8]}")
    os.rename(workdir, target)
    print(f"Warning: quarantined incompatible checkpoint ({reason}) at {target}", file=sys.stderr)


def build_segment_cmd(base_cmd, src, destination, start, duration, has_audio=True):
    """Turn a normal video command into a bounded, timestamp-normalized segment command."""
    cmd = list(base_cmd)
    output = cmd.pop()
    del output
    if cmd[-1] == "-y":
        cmd.pop()
    # Checkpoints always use Matroska segments, even for an eventual MP4 output.
    # Drop output-container-only MP4 flags inherited from the monolithic command.
    while "-movflags" in cmd:
        option = cmd.index("-movflags")
        del cmd[option:option + 2]
    input_at = cmd.index("-i")
    cmd[input_at:input_at] = ["-ss", f"{start:.6f}"]
    # -t is an output option here and must follow the input URL. Inserting it
    # between -i and the URL makes FFmpeg interpret the duration as the input.
    input_at = cmd.index("-i")
    cmd[input_at + 2:input_at + 2] = ["-t", f"{duration:.6f}"]
    # Segment boundaries are deterministic source-time multiples. Seeking makes
    # STARTPTS the selected boundary; forcing zero also normalizes each file.
    insert_at = cmd.index("-c:v")
    if "-vf" in cmd:
        vf = cmd.index("-vf")
        cmd[vf + 1] += ",setpts=PTS-STARTPTS"
    else:
        cmd[insert_at:insert_at] = ["-vf", "setpts=PTS-STARTPTS"]
        insert_at += 2
    cmd[insert_at:insert_at] = ["-force_key_frames", "expr:eq(n,0)"]
    audio_codec = cmd[cmd.index("-c:a") + 1] if "-c:a" in cmd else None
    if has_audio and audio_codec != "copy":
        cmd += ["-af", "asetpts=PTS-STARTPTS"]
    cmd += ["-avoid_negative_ts", "make_zero", "-y", str(destination)]
    return cmd


def transcode_with_checkpoints(src, tmp, profile_name, profile, hw, threads, quality,
                               segment_duration, cuda_decode, progress_args, force_audio_fallback=False):
    """Resume or create independently finalized segments, then concatenate them."""
    workdir = checkpoint_path(src)
    lock = CheckpointLock(workdir)
    lock.acquire()
    active_segment = None
    try:
        source_info = probe_media(src)
        if source_info["video"] < 1 or source_info["duration"] <= 0:
            raise ValueError("source has no video or a non-positive duration")
        expected = {"audio": source_info["audio"],
                    "subtitle": source_info["subtitle"] if profile["out_ext"] == ".mkv" else 0}
        prototype = build_video_cmd(src, Path("SEGMENT.mkv"), profile, hw, threads,
                                    quality_override=quality, cuda_decode=cuda_decode,
                                    force_audio_fallback=force_audio_fallback)
        while "-movflags" in prototype:
            option = prototype.index("-movflags")
            del prototype[option:option + 2]
        signature = checkpoint_signature(src, profile_name, profile, hw, threads, quality,
                                         segment_duration, prototype)
        manifest_path = workdir / "manifest.json"
        manifest = {**signature, "source_duration": source_info["duration"], "completed": []}
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                quarantine_checkpoint(workdir, f"corrupt manifest: {exc}")
                return transcode_with_checkpoints(src, tmp, profile_name, profile, hw, threads,
                                                  quality, segment_duration, cuda_decode, progress_args)
            if any(existing.get(key) != value for key, value in signature.items()):
                quarantine_checkpoint(workdir, "source or encoding settings changed")
                return transcode_with_checkpoints(src, tmp, profile_name, profile, hw, threads,
                                                  quality, segment_duration, cuda_decode, progress_args)
            manifest = existing
        else:
            atomic_json_write(manifest_path, manifest)

        completed = validate_completed_segments(workdir, manifest, expected, manifest_path)

        total_segments = max(1, int((source_info["duration"] + segment_duration - 1e-9) // segment_duration))
        if total_segments * segment_duration < source_info["duration"] - .001:
            total_segments += 1
        for number in range(len(completed), total_segments):
            start = number * segment_duration
            length = min(segment_duration, source_info["duration"] - start)
            active_segment = workdir / f"segment-{number:08d}.writing.mkv"
            active_segment.unlink(missing_ok=True)
            final_segment = workdir / f"segment-{number:08d}.mkv"
            cmd = build_segment_cmd(prototype, src, active_segment, start, length,
                                    has_audio=expected["audio"] > 0)
            rc, stderr = run_ffmpeg_with_progress(cmd, *progress_args, src)
            if rc != 0 and cuda_decode:
                active_segment.unlink(missing_ok=True)
                active_segment = None
                quarantine_checkpoint(workdir, "CUDA decode failed; retrying with CPU decode")
                return transcode_with_checkpoints(
                    src, tmp, profile_name, profile, hw, threads, quality, segment_duration,
                    False, progress_args, force_audio_fallback=force_audio_fallback,
                )
            if rc != 0 or not validate_segment(active_segment, expected, length):
                active_segment.unlink(missing_ok=True)
                active_segment = None
                raise RuntimeError(ffmpeg_error_context(stderr, src))
            os.replace(active_segment, final_segment)
            active_segment = None
            completed.append({"index": number, "file": final_segment.name,
                              "source_start": start, "source_duration": length})
            atomic_json_write(manifest_path, manifest)

        concat_file = workdir / "concat.txt"
        concat_file.write_text("".join(f"file '{(workdir / e['file']).as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n"
                                       for e in completed), encoding="utf-8")
        tmp.unlink(missing_ok=True)
        concat_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-f", "concat", "-safe", "0",
                      "-i", str(concat_file), "-map", "0", "-c", "copy", "-y", str(tmp)]
        rc, stderr = run_ffmpeg(concat_cmd)
        if rc != 0 and not force_audio_fallback and profile["ext"] in {
                ".avi", ".flv", ".m4v", ".mov", ".mpg", ".mpeg", ".rm", ".rmvb", ".wmv"} \
                and is_audio_copy_compat_failure(stderr):
            quarantine_checkpoint(workdir, "audio stream copy is incompatible with the final container")
            return transcode_with_checkpoints(
                src, tmp, profile_name, profile, hw, threads, quality, segment_duration,
                cuda_decode, progress_args, force_audio_fallback=True,
            )
        if rc != 0:
            raise RuntimeError(ffmpeg_error_context(stderr, src))
        combined = probe_media(tmp)
        tolerance = CHECKPOINT_DURATION_TOLERANCE_SECONDS
        if combined["video"] < 1 or combined["audio"] != expected["audio"] \
                or combined["subtitle"] != expected["subtitle"] \
                or abs(combined["duration"] - source_info["duration"]) > tolerance:
            tmp.unlink(missing_ok=True)
            raise ValueError("concatenated checkpoint output failed stream or duration validation")
        return workdir
    except BaseException:
        if active_segment is not None:
            active_segment.unlink(missing_ok=True)
        raise
    finally:
        lock.release()


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


def tmp_age_seconds(path: Path, stat_result=None):
    stat_result = stat_result or path.stat()
    return max(0.0, time.time() - stat_result.st_mtime)


def zero_byte_tmp_claim_is_stale(path: Path, stat_result=None):
    stat_result = stat_result or path.stat()
    return stat_result.st_size == 0 and tmp_age_seconds(path, stat_result) >= ZERO_BYTE_TMP_CLAIM_STALE_SECONDS


def claim_tmp_output(path: Path):
    """Atomically create the temporary output path as a same-directory claim.

    FFmpeg later overwrites this zero-byte file, but creating it before the
    expensive transcode starts lets parallel script invocations notice that the
    source is already claimed and skip it instead of duplicating work.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    os.close(fd)


def reclaim_tmp_output_for_retry(path: Path):
    """Remove failed output and atomically reclaim the temp path before retrying.

    Retry paths intentionally delete FFmpeg's partial output, but the temp path
    must not remain unclaimed between attempts. Recreating the zero-byte claim
    closes the race where another process could claim the same temp output and
    then be overwritten by the retrying FFmpeg command.
    """
    path.unlink(missing_ok=True)
    claim_tmp_output(path)


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
    ap.add_argument("--resume", action="store_true", default=None,
                    help="Use reusable, independently verified segment checkpoints")
    ap.add_argument("--segment-duration", type=float,
                    help="Checkpoint segment length in seconds (default: 300)")
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
    resume_enabled = args.resume if args.resume is not None else config.get("resume", False)
    if not isinstance(resume_enabled, bool):
        print("Error: config key 'resume' must be a boolean", file=sys.stderr)
        return 1
    segment_duration = args.segment_duration if args.segment_duration is not None else config.get("segment_duration", 300)
    if isinstance(segment_duration, bool) or not isinstance(segment_duration, (int, float)) or segment_duration <= 0:
        print("Error: segment duration must be a positive number", file=sys.stderr)
        return 1
    segment_duration = float(segment_duration)
    if resume_enabled and profile["mode"] != "video":
        print("Warning: checkpoint/resume applies only to video profiles; using monolithic audio transcoding.", file=sys.stderr)
        resume_enabled = False

    files = discover_paths(root, args.recurse)
    candidates = []
    for p in files:
        if not p.is_file():
            continue
        if is_checkpoint_internal_path(p):
            continue
        if p.suffix.lower() != profile["ext"]:
            continue
        if is_temporary_transcode_path(p):
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
            checkpoint_to_delete = None
            if tmp.exists():
                if not existing_tmp_is_stable(tmp):
                    print(f"Skipping {src}: temporary output is still changing at {tmp}.", file=sys.stderr)
                    duplicate_skips.append(f"Skipping {src}: temporary output is still changing at {tmp}.")
                    continue
                try:
                    tmp_stat = tmp.stat()
                except FileNotFoundError:
                    msg = f"Skipping {src}: temporary output disappeared before retry at {tmp}."
                    print(msg, file=sys.stderr)
                    duplicate_skips.append(msg)
                    continue
                if tmp_stat.st_size == 0 and not zero_byte_tmp_claim_is_stale(tmp, tmp_stat):
                    msg = f"Skipping {src}: temporary output claim already exists at {tmp}."
                    print(msg, file=sys.stderr)
                    duplicate_skips.append(msg)
                    continue
                print(f"Removing legacy monolithic temporary output before retrying: {tmp}", file=sys.stderr)
                tmp.unlink(missing_ok=True)
            cuda_decode_active = profile["mode"] == "video" and args.hw == "nvenc" and args.cuda_decode
            if resume_enabled:
                try:
                    claim_tmp_output(tmp)
                except FileExistsError:
                    msg = f"Skipping {src}: temporary output claim already exists at {tmp}."
                    print(msg, file=sys.stderr)
                    duplicate_skips.append(msg)
                    continue
                except OSError as exc:
                    print(f"Error: unable to claim temporary output for {src}: {exc}", file=sys.stderr)
                    transcode_failures += 1
                    continue
                active_tmp = tmp
                try:
                    checkpoint_to_delete = transcode_with_checkpoints(
                        src, tmp, args.profile, profile, args.hw, args.threads, selected_quality,
                        segment_duration, cuda_decode_active, (i, len(candidates)),
                    )
                except FileExistsError as exc:
                    tmp.unlink(missing_ok=True)
                    active_tmp = None
                    msg = f"Skipping {src}: {exc}"
                    print(msg, file=sys.stderr)
                    duplicate_skips.append(msg)
                    continue
                except (OSError, ValueError, RuntimeError) as exc:
                    tmp.unlink(missing_ok=True)
                    active_tmp = None
                    print(f"Error: checkpoint transcode failed for {src}: {exc}", file=sys.stderr)
                    transcode_failures += 1
                    continue
                returncode, stderr_text = 0, ""
            else:
                try:
                    claim_tmp_output(tmp)
                except FileExistsError:
                    msg = f"Skipping {src}: temporary output claim already exists at {tmp}."
                    print(msg, file=sys.stderr)
                    duplicate_skips.append(msg)
                    continue
                except OSError as exc:
                    print(f"Error: unable to create temporary output claim for {src}: {exc}", file=sys.stderr)
                    transcode_failures += 1
                    continue
                active_tmp = tmp
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
            if not resume_enabled:
                returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
            if returncode != 0 and cuda_decode_active:
                print(f"CUDA decode failed for {src}; retrying with CPU decode and NVENC encode.", file=sys.stderr)
                cuda_decode_active = False
                try:
                    reclaim_tmp_output_for_retry(tmp)
                except FileExistsError:
                    msg = f"Skipping {src}: temporary output claim already exists at {tmp}."
                    print(msg, file=sys.stderr)
                    duplicate_skips.append(msg)
                    active_tmp = None
                    continue
                except OSError as exc:
                    print(f"Error: unable to reclaim temporary output for retrying {src}: {exc}", file=sys.stderr)
                    transcode_failures += 1
                    active_tmp = None
                    continue
                cmd = build_video_cmd(src, tmp, profile, args.hw, args.threads, quality_override=selected_quality)
                returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
            if returncode != 0:
                if profile["mode"] == "video" and profile["ext"] in {".avi", ".flv", ".m4v", ".mov", ".mpg", ".mpeg", ".rm", ".rmvb", ".wmv"}:
                    fallback_reason = "retrying with a container-compatible audio codec"
                    if not is_audio_copy_compat_failure(stderr_text):
                        print(ffmpeg_error_context(stderr_text, src), file=sys.stderr)
                        transcode_failures += 1
                        if tmp.exists():
                            tmp.unlink()
                        active_tmp = None
                        continue
                    print(f"Audio copy failed for {src}; {fallback_reason}.")
                    try:
                        reclaim_tmp_output_for_retry(tmp)
                    except FileExistsError:
                        msg = f"Skipping {src}: temporary output claim already exists at {tmp}."
                        print(msg, file=sys.stderr)
                        duplicate_skips.append(msg)
                        active_tmp = None
                        continue
                    except OSError as exc:
                        print(f"Error: unable to reclaim temporary output for retrying {src}: {exc}", file=sys.stderr)
                        transcode_failures += 1
                        active_tmp = None
                        continue
                    cmd = build_video_cmd(
                        src,
                        tmp,
                        profile,
                        args.hw,
                        args.threads,
                        quality_override=selected_quality,
                        force_audio_fallback=True,
                        cuda_decode=cuda_decode_active,
                    )
                    returncode, stderr_text = run_ffmpeg_with_progress(cmd, i, len(candidates), src)
                    if returncode != 0 and cuda_decode_active:
                        print(f"CUDA decode failed for {src}; retrying audio fallback with CPU decode and NVENC encode.", file=sys.stderr)
                        try:
                            reclaim_tmp_output_for_retry(tmp)
                        except FileExistsError:
                            msg = f"Skipping {src}: temporary output claim already exists at {tmp}."
                            print(msg, file=sys.stderr)
                            duplicate_skips.append(msg)
                            active_tmp = None
                            continue
                        except OSError as exc:
                            print(f"Error: unable to reclaim temporary output for retrying {src}: {exc}", file=sys.stderr)
                            transcode_failures += 1
                            active_tmp = None
                            continue
                        cmd = build_video_cmd(
                            src,
                            tmp,
                            profile,
                            args.hw,
                            args.threads,
                            quality_override=selected_quality,
                            force_audio_fallback=True,
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

            if checkpoint_to_delete is not None:
                shutil.rmtree(checkpoint_to_delete, ignore_errors=True)

            if profile.get("preserve_source"):
                print(f"Successfully processed {src} -> {out}. Source preserved.")
            else:
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
