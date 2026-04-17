# AGENTS.md - FFmpeg Utility Scripts

## Project Overview

Cross-platform video transcoding scripts that convert MP4 files to H.264 or HEVC/H.265 format with hardware acceleration support.

### Directory Structure
```
ffmpeg_utility_scripts/
├── unix/
│   ├── h264-transcode.sh    # H.264 transcoding (Bash)
│   └── hevc-transcode.sh    # HEVC/H.265 transcoding (Bash)
└── windows/
    ├── h264-transcode.ps1   # H.264 transcoding (PowerShell)
    └── hevc-transcode.ps1   # HEVC transcoding (PowerShell)
```

## Critical Coding Standards

### Bash Scripts (unix/)

#### 1. Strict Mode Requirements
All scripts MUST use these settings:
```bash
set -u  # Fail on unbound variables
shopt -s nullglob    # Globs that match nothing expand to empty
shopt -s nocaseglob  # Case-insensitive glob matching
```

**CRITICAL**: With `set -u`, you cannot:
- Use `local` outside of functions (causes "local: can only be used in a function")
- Reference variables before assignment
- Use `declare -a array` without initializing (use `array=()` instead)

#### 2. Variable Initialization
```bash
# GOOD: Initialize arrays at global scope
files_to_process=()

# BAD: This fails with set -u
local -a files_to_process=()  # Only valid inside functions
declare -a files_to_process   # Doesn't count as assignment for set -u
```

#### 3. Array Usage Patterns
```bash
# Initialize
files_to_process=()

# Append (always quote)
files_to_process+=("$f")

# Iterate (always quote)
for f in "${files_to_process[@]}"; do
    process_file "$f"
done

# Get length
total_files=${#files_to_process[@]}
```

#### 4. Glob Expansion Safety
The scripts use `nullglob` which means:
```bash
for f in *.mp4; do
    # If no .mp4 files exist, this loop doesn't run at all
    # (instead of running once with literal "*.mp4")
done
```

Always check `[[ -f "$f" ]]` before processing in case nullglob is disabled.

#### 5. Quoting Rules

**ALWAYS quote:**
- Filename/path variables: `"$f"`, `"$output"`, `"$temp_out"`
- Variables in test expressions: `[[ "$f" == *_REDU.mp4 ]]`
- Command substitution using filenames: `base_name=$(basename "$f")`

**Never quote (intentional word splitting):**
- `$QUALITY_OPTS` in ffmpeg command (disabled via `# shellcheck disable=SC2086`)

#### 6. Stream Map Selector Quoting
Stream selectors with `?` MUST be quoted to prevent glob expansion:
```bash
# GOOD
-map "0:v:0?" -map "0:a?"

# BAD - ? gets expanded by shell with nullglob
-map 0:v:0? -map 0:a?
```

#### 7. Case-Insensitive Extension Handling
Use parameter expansion for case-insensitive extension stripping:
```bash
# GOOD: Handles .mp4, .MP4, .Mp4, etc.
base_name=$(basename "$f")
base_name="${base_name%.[Mm][Pp]4}"

# BAD: Only handles lowercase .mp4
base_name=$(basename "$f" .mp4)
```

#### 8. Race Condition Prevention
Use atomic operations instead of test-then-act:
```bash
# GOOD: Atomic, no TOCTOU race
if ! mv -n -v -- "$f" "$new_name" 2>/dev/null; then
    echo "Failed to rename (target exists)"
fi

# BAD: Race condition between check and move
if [[ ! -e "$new_name" ]]; then
    mv -- "$f" "$new_name"  # Target could be created here!
fi
```

#### 9. Error Handling
Track failures for proper exit codes:
```bash
# At top of script
FAILED_COUNT=0

# On error
((FAILED_COUNT++))

# At end
exit $(( FAILED_COUNT > 0 ? 1 : 0 ))
```

Check exit codes of critical operations:
```bash
if mv -- "$temp_out" "$output"; then
    if rm -- "$f"; then
        echo "Success"
    else
        echo "Warning: Failed to remove source" >&2
        ((FAILED_COUNT++))
    fi
else
    echo "Error: Move failed" >&2
    ((FAILED_COUNT++))
fi
```

#### 10. Scope Management
```bash
# Inside functions - use local
process_file() {
    local f="$1"
    local output="$dir/${base_name}_REDU.mp4"
    local base_name
    base_name=$(basename "$f")
}

# Main body - no local keyword
files_to_process=()
for f in *.mp4; do
    local output  # This IS valid - inside a loop is function-like scope
    output="${f%.*}_REDU.mp4"
done
```

### FFmpeg Command Patterns

#### Hardware Acceleration
```bash
# Intel QSV (4th gen+)
VIDEO_CODEC="h264_qsv"  # or "hevc_qsv"
QUALITY_OPTS="-global_quality 24"
PRESET="fast"

# NVIDIA NVENC (Maxwell+)
VIDEO_CODEC="h264_nvenc"  # or "hevc_nvenc"
QUALITY_OPTS="-rc vbr -cq 24"
PRESET="p4"

# AMD AMF (Polaris+)
VIDEO_CODEC="h264_amf"  # or "hevc_amf"
QUALITY_OPTS="-qp_p 24 -qp_i 24"
PRESET="speed"

# Software fallback
VIDEO_CODEC="libx264"  # or "libx265"
QUALITY_OPTS="-crf 24"
PRESET="veryfast"
```

#### Stream Mapping
```bash
# Optional stream selection (file can still process if stream missing)
-map "0:v:0?" -map "0:a?"

# Audio copy (may fail with incompatible codecs like DTS)
-c:a copy

# Metadata stripping (prevents stream mismatch errors)
-map_metadata -1
```

### Validation Requirements

#### Audio Stream Count Validation
Always verify audio streams weren't dropped:
```bash
input_audio_streams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$f" 2>/dev/null | wc -l)
output_audio_streams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$temp_out" 2>/dev/null | wc -l)

if [[ "$input_audio_streams" -gt 0 && "$output_audio_streams" -lt "$input_audio_streams" ]]; then
    echo "Error: Audio stream count mismatch" >&2
    ((FAILED_COUNT++))
fi
```

#### File Integrity Checks
```bash
# Verify ffprobe can parse the output
if ffprobe -v error "$temp_out" >/dev/null 2>&1; then
    # File is valid
fi

# Verify file is non-empty
if [[ -s "$temp_out" ]]; then
    # File has content
fi
```

## Testing Changes

### Syntax Validation
```bash
bash -n unix/h264-transcode.sh
bash -n unix/hevc-transcode.sh
```

### ShellCheck
```bash
shellcheck unix/h264-transcode.sh
shellcheck unix/hevc-transcode.sh
```

### Test Scenarios
When modifying scripts, verify these edge cases:
1. Empty directory (no .mp4 files)
2. Directory with only already-processed files
3. Files with spaces in names
4. Files with mixed-case extensions (.MP4, .Mp4)
5. Files with newlines in names (should be rejected)
6. Files with incompatible audio codecs (DTS in MKV container)
7. Video-only files (no audio)
8. Audio-only files (no video)
9. Interrupt during processing (Ctrl+C)

## Known Limitations

1. **Audio Copy Risk**: `-c:a copy` may fail with incompatible codecs (DTS, FLAC, etc.). The scripts validate stream count but don't re-encode on failure.

2. **Metadata Stripping**: `-map_metadata -1` removes ALL metadata including rotation tags. Mobile videos may lose orientation.

3. **Subtitle Loss**: Subtitle streams are not mapped and will be lost.

4. **Hardware Compatibility**: Hardware encoders require specific CPU/GPU generations. Script falls back to software encoding only if not requested.

## Common Pitfalls

### Don't Use `local` in Main Body
```bash
# WRONG - will error with "local: can only be used in a function"
local -a files_to_process=()

# CORRECT
files_to_process=()
```

### Don't Forget `local` in Loops
```bash
# WRONG - pollutes global namespace
for f in *.mp4; do
    output="${f%.*}_REDU.mp4"
done

# CORRECT
for f in *.mp4; do
    local output
    output="${f%.*}_REDU.mp4"
done
```

### Quote Stream Selectors
```bash
# WRONG - ? gets glob-expanded
-map 0:v:0?

# CORRECT
-map "0:v:0?"
```

## Script Suffix Conventions

- H.264 output: `_REDU.mp4`
- HEVC output: `_HEVC.mp4`
- Temp files: `._REDU.tmp.mp4` or `._HEVC.tmp.mp4`

## Exit Codes

- `0`: Success (all files processed, or no eligible files found)
- `1`: Failure (one or more files failed to process, or invalid arguments)

## Related Documentation

- FFmpeg codecs: https://ffmpeg.org/ffmpeg-codecs.html
- Hardware acceleration: https://trac.ffmpeg.org/wiki/HWAccelIntro
- Bash strict mode: http://redsymbol.net/articles/unofficial-bash-strict-mode/
