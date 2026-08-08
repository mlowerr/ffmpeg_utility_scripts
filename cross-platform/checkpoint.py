#!/usr/bin/env python3
"""Checkpoint/resume machinery: locks, manifests, segment commands, and orchestration.

Cross-module calls intentionally go through module attributes (ffmpeg.*,
output.*, profiles.*) so tests can patch a single module namespace.
"""
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import ffmpeg
import output
import profiles

CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_LOCK_STALE_SECONDS = 48 * 60 * 60
CHECKPOINT_DURATION_TOLERANCE_SECONDS = 0.5


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
        created = False
        try:
            self.directory.mkdir()
            created = True
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
                created = True
            except OSError as exc:
                raise FileExistsError(f"could not recover checkpoint lock: {exc}") from exc
        try:
            output.atomic_json_write(self.directory / "owner.json", self.owner)
        except BaseException:
            # A directory without its ownership record blocks all other users
            # until the long stale-lock lease expires. Remove only the lock
            # directory created by this acquisition attempt.
            if created:
                shutil.rmtree(self.directory, ignore_errors=True)
            raise

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
        actual = ffmpeg.probe_media(path)
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
            output.atomic_json_write(manifest_path, manifest)
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


class CheckpointStateError(Exception):
    """Internal signal that checkpoint state must be rebuilt and the run restarted."""

    def __init__(self, reason, cuda_decode=None, force_audio_fallback=None):
        super().__init__(reason)
        self.reason = reason
        self.cuda_decode = cuda_decode
        self.force_audio_fallback = force_audio_fallback


def transcode_with_checkpoints(src, tmp, profile_name, profile, hw, threads, quality,
                               segment_duration, cuda_decode, progress_args, force_audio_fallback=False):
    """Resume or create independently finalized segments, then concatenate them."""
    while True:
        try:
            return _checkpoint_run(src, tmp, profile_name, profile, hw, threads, quality,
                                   segment_duration, cuda_decode, progress_args, force_audio_fallback)
        except CheckpointStateError as exc:
            quarantine_checkpoint(checkpoint_path(src), exc.reason)
            cuda_decode = exc.cuda_decode if exc.cuda_decode is not None else cuda_decode
            force_audio_fallback = (
                exc.force_audio_fallback if exc.force_audio_fallback is not None else force_audio_fallback
            )


def _checkpoint_run(src, tmp, profile_name, profile, hw, threads, quality,
                    segment_duration, cuda_decode, progress_args, force_audio_fallback=False):
    """Resume or create independently finalized segments, then concatenate them."""
    workdir = checkpoint_path(src)
    lock = CheckpointLock(workdir)
    lock.acquire()
    active_segment = None
    try:
        source_info = ffmpeg.probe_media(src)
        if source_info["video"] < 1 or source_info["duration"] <= 0:
            raise ValueError("source has no video or a non-positive duration")
        expected = {"audio": source_info["audio"],
                    "subtitle": source_info["subtitle"] if profile["out_ext"] == ".mkv" else 0}
        fallback_audio_streams = ffmpeg.probe_audio_streams(src) if force_audio_fallback else None
        prototype = ffmpeg.build_video_cmd(src, Path("SEGMENT.mkv"), profile, hw, threads,
                                           quality_override=quality, cuda_decode=cuda_decode,
                                           force_audio_fallback=force_audio_fallback,
                                           audio_streams=fallback_audio_streams)
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
                raise CheckpointStateError(f"corrupt manifest: {exc}")
            if any(existing.get(key) != value for key, value in signature.items()):
                raise CheckpointStateError("source or encoding settings changed")
            manifest = existing
        else:
            output.atomic_json_write(manifest_path, manifest)

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
            rc, stderr = ffmpeg.run_ffmpeg_with_progress(cmd, *progress_args, src)
            if rc != 0 and cuda_decode:
                active_segment.unlink(missing_ok=True)
                active_segment = None
                raise CheckpointStateError("CUDA decode failed; retrying with CPU decode",
                                           cuda_decode=False)
            if rc != 0 or not validate_segment(active_segment, expected, length):
                active_segment.unlink(missing_ok=True)
                active_segment = None
                raise RuntimeError(ffmpeg.ffmpeg_error_context(stderr, src))
            os.replace(active_segment, final_segment)
            active_segment = None
            completed.append({"index": number, "file": final_segment.name,
                              "source_start": start, "source_duration": length})
            output.atomic_json_write(manifest_path, manifest)

        concat_file = workdir / "concat.txt"
        concat_file.write_text("".join(f"file '{(workdir / e['file']).as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n"
                                       for e in completed), encoding="utf-8")
        tmp.unlink(missing_ok=True)
        concat_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-f", "concat", "-safe", "0",
                      "-i", str(concat_file), "-map", "0", "-c", "copy", "-y", str(tmp)]
        rc, stderr = ffmpeg.run_ffmpeg(concat_cmd)
        if rc != 0 and not force_audio_fallback and profile["ext"] in profiles.AUDIO_COPY_FALLBACK_EXTENSIONS \
                and ffmpeg.is_audio_copy_compat_failure(stderr):
            raise CheckpointStateError("audio stream copy is incompatible with the final container",
                                       force_audio_fallback=True)
        if rc != 0:
            raise RuntimeError(ffmpeg.ffmpeg_error_context(stderr, src))
        combined = ffmpeg.probe_media(tmp)
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
