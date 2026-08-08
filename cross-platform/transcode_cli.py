#!/usr/bin/env python3
"""Cross-platform FFmpeg transcoding CLI.

This module is the orchestration and command-line layer. Implementation lives
in sibling modules (ffmpeg.py, checkpoint.py, output.py, profiles.py) which
are called through module attributes so tests can patch one namespace
(cli.ffmpeg.X / cli.checkpoint.Y / ...).
"""
import argparse
import shutil
import signal
import subprocess
import sys
from pathlib import Path

# Allow sibling-module imports when this file is loaded through importlib
# (test harness) where the script directory is not automatically on sys.path.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import checkpoint
import ffmpeg
import output
import profiles

# Backwards-compatible re-exports for the CLI surface used by tests and drivers.
from checkpoint import (
    CheckpointLock,
    CheckpointStateError,
    CHECKPOINT_DURATION_TOLERANCE_SECONDS,
    CHECKPOINT_LOCK_STALE_SECONDS,
    CHECKPOINT_SCHEMA_VERSION,
    build_segment_cmd,
    checkpoint_path,
    checkpoint_signature,
    quarantine_checkpoint,
    transcode_with_checkpoints,
    validate_completed_segments,
    validate_segment,
)
from ffmpeg import (
    build_audio_cmd,
    build_video_cmd,
    cuda_scale_filter,
    detect_dimensions,
    ffmpeg_error_context,
    ffmpeg_filter_names,
    ffprobe_ok,
    format_audio_streams,
    is_audio_copy_compat_failure,
    probe_audio_streams,
    probe_media,
    run_capture,
    run_ffmpeg,
    run_ffmpeg_with_progress,
    wmv_needs_timing_normalization,
)
from output import (
    ZERO_BYTE_TMP_CLAIM_STALE_SECONDS,
    atomic_json_write,
    claim_tmp_output,
    copy_output_no_overwrite,
    existing_tmp_is_stable,
    finalize_output_no_overwrite,
    normalize_input_name,
    out_name,
    reclaim_tmp_output_for_retry,
    tmp_age_seconds,
    zero_byte_tmp_claim_is_stale,
)
from profiles import (
    AUDIO_COPY_FALLBACK_EXTENSIONS,
    PROFILES,
    default_config_path,
    discover_paths,
    effective_quality,
    is_checkpoint_internal_path,
    is_path_under,
    is_temporary_transcode_path,
    load_user_config,
    normalize_skip_dirs,
    should_skip_file,
    validate_quality_value,
)


class TranscodeJob:
    """Encapsulated per-invocation transcode configuration."""

    def __init__(self, profile_name, profile, hw, threads, quality, resume,
                 segment_duration, cuda_decode):
        self.profile_name = profile_name
        self.profile = profile
        self.hw = hw
        self.threads = threads
        self.quality = quality
        self.resume = resume
        self.segment_duration = segment_duration
        self.cuda_decode = cuda_decode


class TranscodeSession:
    """Per-invocation counters and summary output shared with the signal handler."""

    def __init__(self):
        self.failures = 0
        self.failure_records = []
        self.cleanup_warnings = 0
        self.duplicate_skips = []
        self.active_tmp = None
        self.interrupted = False

    def record_failure(self, source, stage, reason):
        self.failures += 1
        self.failure_records.append({"source": str(source), "stage": stage, "reason": str(reason)})

    def skip(self, message):
        self.duplicate_skips.append(message)
        print(message, file=sys.stderr)


def video_attempt_chain(profile, cuda_decode):
    """Return the ordered retry attempts for a video transcode.

    The primary pass always runs first. When CUDA was requested, a CPU-decode
    retry follows a failure. Legacy profiles then retry with a container-
    compatible audio codec, but only when the failed pass reported an audio
    stream-copy compatibility error (the compat gate).
    """
    attempts = [
        {"cuda_decode": cuda_decode, "force_audio_fallback": False,
         "gate": False, "prep_stage": None},
    ]
    if cuda_decode:
        attempts.append({"cuda_decode": False, "force_audio_fallback": False,
                         "gate": False, "prep_stage": "CUDA retry preparation"})
    if profile["ext"] in profiles.AUDIO_COPY_FALLBACK_EXTENSIONS:
        attempts.append({"cuda_decode": cuda_decode, "force_audio_fallback": True,
                         "gate": True, "prep_stage": "audio fallback preparation"})
        if cuda_decode:
            attempts.append({"cuda_decode": False, "force_audio_fallback": True,
                             "gate": False, "prep_stage": "CUDA audio fallback preparation"})
    return attempts


def run_video_with_retries(src, tmp, job, progress_args):
    """Run the video ffmpeg flow with CUDA-decode and audio-copy retries.

    Returns ("ok", None, None) on success; otherwise ("status", stage, detail)
    with status in {"hard-failure", "skip-claim", "retry-failure",
    "probe-failure"}.
    """
    attempts = video_attempt_chain(job.profile, job.cuda_decode)
    fallback_streams = None
    last_stderr = ""
    fallback_attempted = False
    for index, attempt in enumerate(attempts):
        if attempt["gate"] and not ffmpeg.is_audio_copy_compat_failure(last_stderr):
            return "hard-failure", "FFmpeg transcode", last_stderr
        if index > 0:
            try:
                output.reclaim_tmp_output_for_retry(tmp)
            except FileExistsError:
                return "skip-claim", attempt["prep_stage"], None
            except OSError as exc:
                return "retry-failure", attempt["prep_stage"], exc
        if attempt["force_audio_fallback"]:
            if not fallback_attempted:
                print(f"Audio copy failed for {src}; retrying with a container-compatible audio codec.",
                      file=sys.stderr)
                fallback_attempted = True
            if fallback_streams is None:
                try:
                    fallback_streams = ffmpeg.probe_audio_streams(src)
                except RuntimeError as exc:
                    return "probe-failure", "audio fallback probe", exc
        cmd = ffmpeg.build_video_cmd(src, tmp, job.profile, job.hw, job.threads,
                                     quality_override=job.quality,
                                     force_audio_fallback=attempt["force_audio_fallback"],
                                     cuda_decode=attempt["cuda_decode"],
                                     audio_streams=fallback_streams)
        returncode, last_stderr = ffmpeg.run_ffmpeg_with_progress(cmd, *progress_args, src)
        if returncode == 0:
            return "ok", None, None
    stage = "audio fallback transcode" if fallback_attempted else "FFmpeg transcode"
    return "hard-failure", stage, last_stderr


def process_one(session, original_src, index, total, job):
    """Transcode one candidate file, recording outcomes in the session."""
    src, _ = output.normalize_input_name(original_src)
    out, tmp = output.out_name(src, job.profile)
    progress_args = (index, total)

    if out.exists():
        session.skip(f"Skipping {src}: converted output already exists at {out} (possible duplicate after normalization).")
        return
    if tmp.exists():
        if not output.existing_tmp_is_stable(tmp):
            session.skip(f"Skipping {src}: temporary output is still changing at {tmp}.")
            return
        try:
            tmp_stat = tmp.stat()
        except FileNotFoundError:
            session.skip(f"Skipping {src}: temporary output disappeared before retry at {tmp}.")
            return
        if tmp_stat.st_size == 0 and not output.zero_byte_tmp_claim_is_stale(tmp, tmp_stat):
            session.skip(f"Skipping {src}: temporary output claim already exists at {tmp}.")
            return
        print(f"Removing legacy monolithic temporary output before retrying: {tmp}", file=sys.stderr)
        tmp.unlink(missing_ok=True)

    try:
        output.claim_tmp_output(tmp)
    except FileExistsError:
        session.skip(f"Skipping {src}: temporary output claim already exists at {tmp}.")
        return
    except OSError as exc:
        session.record_failure(src, "temporary output claim", exc)
        print(f"Error: unable to claim temporary output for {src}: {exc}", file=sys.stderr)
        return
    session.active_tmp = tmp

    checkpoint_to_delete = None
    if job.resume:
        try:
            checkpoint_to_delete = checkpoint.transcode_with_checkpoints(
                src, tmp, job.profile_name, job.profile, job.hw, job.threads, job.quality,
                job.segment_duration, job.cuda_decode, (index, total),
            )
        except FileExistsError as exc:
            tmp.unlink(missing_ok=True)
            session.skip(f"Skipping {src}: {exc}")
            return
        except (OSError, ValueError, RuntimeError) as exc:
            tmp.unlink(missing_ok=True)
            print(f"Error: checkpoint transcode failed for {src}: {exc}", file=sys.stderr)
            session.record_failure(src, "checkpoint transcode", exc)
            return
    else:
        if job.profile["mode"] == "audio":
            try:
                returncode, stderr_text = ffmpeg.run_ffmpeg_with_progress(
                    ffmpeg.build_audio_cmd(src, tmp), *progress_args, src)
            except (OSError, UnicodeError) as exc:
                print(f"Error: unable to launch or read FFmpeg for {src}: {exc}", file=sys.stderr)
                session.record_failure(src, "FFmpeg invocation", exc)
                tmp.unlink(missing_ok=True)
                return
            if returncode != 0:
                print(ffmpeg.ffmpeg_error_context(stderr_text, src), file=sys.stderr)
                session.record_failure(src, "FFmpeg transcode", "FFmpeg failed; see diagnostics above")
                tmp.unlink(missing_ok=True)
                return
        else:
            try:
                status, stage, payload = run_video_with_retries(src, tmp, job, progress_args)
            except (OSError, UnicodeError) as exc:
                print(f"Error: unable to launch or read FFmpeg/FFprobe for {src}: {exc}", file=sys.stderr)
                session.record_failure(src, "FFmpeg invocation", exc)
                tmp.unlink(missing_ok=True)
                return
            if status == "skip-claim":
                session.skip(f"Skipping {src}: temporary output claim already exists at {tmp}.")
                return
            if status == "retry-failure":
                print(f"Error: unable to reclaim temporary output for retrying {src}: {payload}",
                      file=sys.stderr)
                session.record_failure(src, stage, payload)
                return
            if status == "probe-failure":
                print(f"Error: unable to probe audio streams for fallback on {src}: {payload}",
                      file=sys.stderr)
                session.record_failure(src, stage, payload)
                tmp.unlink(missing_ok=True)
                return
            if status == "hard-failure":
                print(ffmpeg.ffmpeg_error_context(payload, src), file=sys.stderr)
                session.record_failure(src, stage, "FFmpeg failed; see diagnostics above")
                tmp.unlink(missing_ok=True)
                return

    try:
        output_is_valid = tmp.exists() and tmp.stat().st_size > 0 and ffmpeg.ffprobe_ok(tmp)
    except (OSError, UnicodeError) as exc:
        print(f"Error: unable to launch or read FFprobe for {src}: {exc}", file=sys.stderr)
        session.record_failure(src, "output verification", exc)
        tmp.unlink(missing_ok=True)
        return
    if not output_is_valid:
        print(f"Error: Output verification failed for {src}", file=sys.stderr)
        session.record_failure(src, "output verification", "temporary output is missing, empty, or unreadable")
        tmp.unlink(missing_ok=True)
        return
    if job.profile["mode"] == "video":
        try:
            input_audio = ffmpeg.probe_audio_streams(src)
            output_audio = ffmpeg.probe_audio_streams(tmp)
        except RuntimeError as exc:
            print(f"Error: Audio stream validation failed for {src}: {exc}", file=sys.stderr)
            session.record_failure(src, "audio stream probe", exc)
            tmp.unlink(missing_ok=True)
            return
        if input_audio and len(output_audio) < len(input_audio):
            reason = (
                f"input audio streams: {len(input_audio)}; output audio streams: {len(output_audio)}; "
                f"input details: [{ffmpeg.format_audio_streams(input_audio)}]; "
                f"output details: [{ffmpeg.format_audio_streams(output_audio)}]"
            )
            print(f"Error: Audio stream mismatch for {src}: {reason}", file=sys.stderr)
            session.record_failure(src, "audio stream validation", reason)
            tmp.unlink(missing_ok=True)
            return

    try:
        finalized_tmp_removed = output.finalize_output_no_overwrite(tmp, out)
    except FileExistsError:
        print(f"Error: Destination already exists for {src}: {out}", file=sys.stderr)
        session.record_failure(src, "output finalize", f"destination already exists: {out}")
        tmp.unlink(missing_ok=True)
        return
    except Exception as exc:
        print(f"Error moving temporary output into place for {src}: {exc}", file=sys.stderr)
        session.record_failure(src, "output finalize", exc)
        tmp.unlink(missing_ok=True)
        return

    if not finalized_tmp_removed:
        print(f"Warning: Output finalized at {out}, but failed to remove temporary hard link {tmp}.",
              file=sys.stderr)
        session.cleanup_warnings += 1

    if checkpoint_to_delete is not None:
        shutil.rmtree(checkpoint_to_delete, ignore_errors=True)

    if job.profile.get("preserve_source"):
        print(f"Successfully processed {src} -> {out}. Source preserved.")
    else:
        try:
            src.unlink()
            print(f"Successfully processed {src} -> {out}")
        except Exception as exc:
            print(f"Error deleting source after successful output finalize for {src}: {exc}. "
                  f"Output kept at {out}.", file=sys.stderr)
            session.cleanup_warnings += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, choices=sorted(profiles.PROFILES))
    ap.add_argument("--path", default=".")
    ap.add_argument("-r", "--recurse", dest="recurse", action="store_true")
    ap.add_argument("--hw", choices=["software", "qsv", "nvenc", "amf", "auto"], default="software")
    ap.add_argument("-q", "--quick-sync", dest="hw", action="store_const", const="qsv",
                    help="Legacy alias for --hw qsv (Intel Quick Sync)")
    ap.add_argument("-n", "--nvenc", dest="hw", action="store_const", const="nvenc",
                    help="Legacy alias for --hw nvenc (NVIDIA)")
    ap.add_argument("-a", "--amf", dest="hw", action="store_const", const="amf",
                    help="Legacy alias for --hw amf (AMD)")
    ap.add_argument("-t", "--threads", type=int,
                    help="Thread count for software encoding (legacy -t alias)")
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

    profile = profiles.PROFILES[args.profile]
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

    config_path = Path(args.config).expanduser().resolve() if args.config else profiles.default_config_path()
    try:
        config = profiles.load_user_config(config_path, required=bool(args.config))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    config_skip_dirs = config.get("skip_dirs", [])
    if not isinstance(config_skip_dirs, list):
        print("Error: config key 'skip_dirs' must be a list", file=sys.stderr)
        return 1
    raw_skip_dirs = [*config_skip_dirs, *args.skip_dir]
    if any(not isinstance(d, str) or not d for d in raw_skip_dirs):
        print("Error: skip directory entries must be non-empty strings", file=sys.stderr)
        return 1
    skip_dirs = profiles.normalize_skip_dirs(raw_skip_dirs, root)
    try:
        selected_quality = profiles.effective_quality(args.profile, profile, config, args.quality)
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

    files = profiles.discover_paths(root, args.recurse)
    candidates = []
    rejected_filenames = 0
    for p in files:
        if not p.is_file():
            continue
        if profiles.is_checkpoint_internal_path(p):
            continue
        if p.suffix.lower() != profile["ext"]:
            continue
        if profiles.has_unsafe_filename(p):
            print(
                f"Error: filename contains a newline or carriage return: {str(p)!r}",
                file=sys.stderr,
            )
            rejected_filenames += 1
            continue
        if profiles.is_temporary_transcode_path(p):
            continue
        if args.profile == "h264_mpg" and p.name.lower().endswith("_redu.mpg"):
            # Avoid reprocessing RM/RMVB outputs (and other already reduced MPG names)
            # into *_REDU_REDU.mp4 on subsequent runs.
            continue
        if profiles.should_skip_file(p.resolve(), skip_dirs):
            continue
        out, _ = output.out_name(p, profile)
        if profile["suffix"] and p.name.lower().endswith((profile["suffix"] + profile["out_ext"]).lower()):
            continue
        if out.exists():
            continue
        candidates.append(p)
    candidates = sorted(candidates, key=lambda item: str(item).lower())

    if not candidates:
        print(f"No eligible {profile['ext']} files found to process.")
        return 1 if rejected_filenames else 0

    session = TranscodeSession()

    def cleanup_and_exit(signum, _frame):
        session.interrupted = True
        if session.active_tmp and session.active_tmp.exists():
            session.active_tmp.unlink(missing_ok=True)
        raise KeyboardInterrupt(f"Signal {signum}")

    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    cuda_decode_active = profile["mode"] == "video" and args.hw == "nvenc" and args.cuda_decode
    job = TranscodeJob(
        profile_name=args.profile,
        profile=profile,
        hw=args.hw,
        threads=args.threads,
        quality=selected_quality,
        resume=resume_enabled,
        segment_duration=segment_duration,
        cuda_decode=cuda_decode_active,
    )

    try:
        for index, original_src in enumerate(candidates, 1):
            print(f"\n\nProcessing file {index} of {len(candidates)}\n")
            process_one(session, original_src, index, len(candidates), job)
            session.active_tmp = None
    except KeyboardInterrupt:
        session.interrupted = True
        print("\nInterrupted. Cleaned up active temporary output file.", file=sys.stderr)
        session.record_failure(session.active_tmp or "active transcode", "interrupt",
                               "processing was interrupted")
    finally:
        if session.duplicate_skips:
            print("\nDuplicate-skip summary:", file=sys.stderr)
            for entry in session.duplicate_skips:
                print(f"- {entry}", file=sys.stderr)
        if session.cleanup_warnings:
            print(
                f"\nCleanup warning summary: {session.cleanup_warnings} source cleanup issue(s). Output files were kept.",
                file=sys.stderr,
            )
        if session.failure_records:
            if session.interrupted:
                summary_suffix = "processing was interrupted; remaining files were not attempted."
            else:
                summary_suffix = "processing continued."
            print(
                f"\nFailure summary: {len(session.failure_records)} file operation(s) failed; {summary_suffix}",
                file=sys.stderr,
            )
            for failure in session.failure_records:
                print(
                    f"- {failure['source']} [{failure['stage']}]: {failure['reason']}",
                    file=sys.stderr,
                )

    hard_failures = session.failures + rejected_filenames
    if args.strict_cleanup:
        hard_failures += session.cleanup_warnings

    return 1 if hard_failures > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
