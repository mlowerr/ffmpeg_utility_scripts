#!/usr/bin/env python3
"""Output naming, atomic temporary-output claiming, and no-overwrite finalization."""
import errno
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

ZERO_BYTE_TMP_CLAIM_STALE_SECONDS = 45 * 60


def atomic_json_write(path: Path, value):
    pending = path.with_name(path.name + f".{uuid.uuid4().hex}.pending")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, path)


def out_name(p: Path, profile):
    if profile["mode"] == "audio":
        return p.with_suffix(".mp3"), p.with_suffix(".tmp.mp3")
    stem = p.stem + profile["suffix"]
    return p.with_name(stem + profile["out_ext"]), p.with_name(stem + ".tmp" + profile["out_ext"])


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
