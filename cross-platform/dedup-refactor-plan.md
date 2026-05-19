# Cross-Platform Deduplication Plan (Unix + Windows)

This document defines the target module structure and CLI contract for reducing duplicate logic between Bash (`unix/`) and PowerShell (`windows/`) transcode scripts.

## Goals

- Keep existing script entrypoints stable for users.
- Centralize shared behavior (discovery, naming, ffmpeg/ffprobe execution, validation, and reporting).
- Move encoder/profile differences to declarative config.
- Preserve script conventions already used in this repo (`_REDU`, `_HEVC`, `.tmp`, exit codes).

## Target Architecture

```text
cross-platform/
├── transcode_cli.py          # Main executable CLI entrypoint
├── transcode_core.py         # Shared orchestration and file processing
├── profiles.py               # Declarative profile definitions
├── encoder_resolver.py       # Hardware/software encoder option mapping
├── io_discovery.py           # File collection, skip detection, name derivation
├── ffmpeg_runner.py          # ffmpeg/ffprobe command execution and checks
├── validators.py             # Output parseability, stream-count, size checks
└── compat_wrappers/          # Optional wrapper-specific arg adapters
```

### Module Responsibilities

- `transcode_cli.py`
  - Parses top-level arguments.
  - Resolves profile + hardware mode.
  - Calls core `run_batch()` and returns exit code.

- `transcode_core.py`
  - High-level orchestration (`discover -> process -> validate -> summarize`).
  - Failure counting and final exit status.
  - Logging for progress and per-file outcome.

- `profiles.py`
  - Defines all workflow profiles in one table.
  - Encapsulates output naming, extension matching, mapping mode, audio policy, quality defaults.

- `encoder_resolver.py`
  - Converts profile + `--hw` selection into codec/preset/quality options.
  - Supports `qsv`, `nvenc`, `amf`, `software`, and `auto`.

- `io_discovery.py`
  - Case-insensitive extension matching.
  - Optional recursive discovery.
  - Skip logic for already-processed outputs.
  - Temp/output file path derivation.

- `ffmpeg_runner.py`
  - Builds and executes ffmpeg argument lists.
  - Handles process errors and stderr reporting.
  - Runs ffprobe helper calls.

- `validators.py`
  - `ffprobe` parseability check.
  - Non-empty output check.
  - Audio stream count parity where applicable.

## Profile Contract

Profiles should be data-only objects keyed by ID.

Recommended IDs:

- `h264_mp4`
- `h264_avi`
- `h264_mov`
- `h264_mpg`
- `h264_flv`
- `h264_wmv`
- `hevc_mp4`
- `hevc_mkv`
- `flac_mp3`
- `wav_mp3`

Required fields per profile:

- `input_exts`: list of accepted extensions (case-insensitive)
- `output_ext`: output extension (`.mp4`, `.mkv`, `.mp3`)
- `output_suffix`: e.g. `_REDU`, `_HEVC`, or empty for mp3 conversion
- `temp_suffix`: e.g. `_REDU.tmp.mp4`, `_HEVC.tmp.mkv`, `.tmp.mp3`
- `media_type`: `video` or `audio`
- `map_mode`: stream mapping behavior (`video_optional_audio_optional`, `audio_only`, etc.)
- `audio_mode`: `copy` / `encode` / `none`
- `strip_metadata`: boolean
- `quality_baseline`: quality number defaults by encoder family
- `wmv_quality_override`: explicit WMV quality exception (24)

## Unified CLI Contract

Primary command:

```bash
python3 cross-platform/transcode_cli.py --profile <id> [options]
```

### Core options

- `--profile <id>` (required): workflow profile key.
- `--path <dir>` (default: current directory): root directory to scan.
- `--recursive` (flag): recurse into subdirectories.
- `--hw {auto,qsv,nvenc,amf,software}` (default: `software`).
- `--threads <n>` (optional): explicit thread count pass-through.
- `--overwrite` (flag): allow replacing outputs when explicitly requested.
- `--dry-run` (flag): print planned actions without transcoding.
- `--verbose` (flag): emit ffmpeg command lines and ffprobe details.

### Compatibility alias options (for wrapper passthrough)

- Unix aliases:
  - `-r` => `--recursive`
  - `-q` => `--hw qsv`
  - `-n` => `--hw nvenc`
  - `-a` => `--hw amf`
  - `-t N` => `--threads N`

- Windows aliases:
  - `-Recurse` => `--recursive`
  - `-UseQuickSync` => `--hw qsv`
  - `-UseNVENC` => `--hw nvenc`
  - `-UseAMF` => `--hw amf`
  - `-Threads N` => `--threads N`

### Exit codes

- `0`: all eligible files succeeded, or no eligible files found.
- `1`: one or more files failed, or invalid argument combination.

## Wrapper Strategy

Keep each existing script filename, but reduce each wrapper to:

1. Parse legacy flags.
2. Map to profile + normalized CLI args.
3. Invoke `python3 cross-platform/transcode_cli.py ...` (or `py -3` on Windows).
4. Return the Python process exit code.

Examples:

- `unix/h264-transcode.sh` -> `--profile h264_mp4`
- `unix/h264-wmv-transcode.sh` -> `--profile h264_wmv`
- `windows/hevc-transcode.ps1` -> `--profile hevc_mp4`
- `windows/flac-to-mp3.ps1` -> `--profile flac_mp3`

## Rollout Sequence

1. Add `profiles.py`, `encoder_resolver.py`, and `transcode_cli.py` without wrapper migration.
2. Migrate one paired workflow first (`h264-transcode.sh` + `h264-transcode.ps1`) and validate parity.
3. Migrate remaining H.264 extension variants (`avi/mov/mpg/flv/wmv`).
4. Migrate HEVC MP4 + HEVC MKV workflows.
5. Migrate FLAC/WAV audio conversion workflows.
6. Remove duplicated logic that is fully replaced by core modules.

## Acceptance Criteria

- Existing script names still work.
- Output naming and temp naming conventions are unchanged.
- WMV quality behavior remains at quality 24.
- Stream-map selector behavior and validation checks are preserved.
- Unix and Windows runs produce equivalent success/failure semantics.
- No regression in handling mixed-case extensions, spaces, or empty directories.
