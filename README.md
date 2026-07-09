# FFmpeg Utility Scripts

A collection of cross-platform FFmpeg utility scripts. Supports H.264 and HEVC/H.265 video encoding with optional hardware acceleration, plus FLAC/WAV audio conversion to 256 kbps MP3.

## Features

- **Cross-platform**: Bash scripts for Linux/macOS, PowerShell scripts for Windows, and Python scripts for portable reporting
- **Codec support**: H.264 (AVC) and HEVC/H.265 encoding
- **Audio conversion**: FLAC and WAV to 256 kbps MP3
- **Hardware acceleration**: Intel Quick Sync, NVIDIA NVENC, AMD AMF
- **Batch processing**: Process single directory or recursively
- **Safe operation**: Verifies output integrity before deleting source files
- **Progress tracking**: Shows "Processing file X of Y" for batch operations
- **Smart 4K downscaling**: Automatically downscales 4K+ video to aspect-safe 1080p
- **Smart file handling**: Renames each file with spaces at encode time (spaces → underscores), skips already-processed files
- **File type reporting**: Counts files by extension, lists matching full file paths, and generates per-folder reports

## Repository Structure

```
.
├── cross-platform/
│   ├── file-type-report.py        # Count files by file type (Python, cross-platform)
│   ├── files-by-extension.py      # List full paths matching an extension (Python, cross-platform)
│   ├── recursive-file-type-report.py # Per-folder type reports (Python, cross-platform)
│   ├── one-level-recursive-file-type-report.py # Combined child-folder reports
│   └── hevc-mkv-transcode.py      # HEVC/H.265 encoding for MKV (Python, cross-platform)
├── unix/
│   ├── video/
│   │   ├── h264-transcode.sh
│   │   ├── h264-avi-transcode.sh
│   │   ├── h264-mov-transcode.sh
│   │   ├── h264-m4v-transcode.sh
│   │   ├── h264-mpg-transcode.sh
│   │   ├── h264-mpeg-transcode.sh
│   │   ├── h264-flv-transcode.sh
│   │   ├── h264-wmv-transcode.sh
│   │   ├── hevc-transcode.sh
│   │   ├── hevc-mkv-transcode.sh
│   │   └── transcode_all_video.sh
│   └── audio/
│       ├── flac-to-mp3.sh
│       ├── wav-to-mp3.sh
│       └── transcode_all_audio.sh
├── windows/
│   ├── video/
│   │   ├── h264-transcode.ps1
│   │   ├── h264-avi-transcode.ps1
│   │   ├── h264-mov-transcode.ps1
│   │   ├── h264-m4v-transcode.ps1
│   │   ├── h264-mpg-transcode.ps1
│   │   ├── h264-mpeg-transcode.ps1
│   │   ├── h264-flv-transcode.ps1
│   │   ├── h264-wmv-transcode.ps1
│   │   ├── hevc-transcode.ps1
│   │   ├── hevc-mkv-transcode.ps1
│   │   └── transcode_all_video.ps1
│   └── audio/
│       ├── flac-to-mp3.ps1
│       ├── wav-to-mp3.ps1
│       └── transcode_all_audio.ps1
├── HARDWARE_ACCEL_GUIDE.md        # Hardware acceleration setup guide
└── README.md                      # This file
```

## Requirements

- **FFmpeg** 4.0 or later (must be in PATH)
- **Bash** 4.0+ (for Unix scripts)
- **PowerShell** 5.1+ (for Windows scripts)
- **ffprobe** (for output verification)
- **Python** 3.10+ recommended (3.9+ supported) for cross-platform Python scripts

### Python Setup (especially for Windows users)

Use a modern Python 3 build so `pathlib`/argument handling behavior is consistent across platforms.

**Recommended version:** Python **3.10, 3.11, or 3.12**.

**Windows install options:**
```powershell
# Option 1 (recommended): install from python.org with "Add python.exe to PATH" enabled
# https://www.python.org/downloads/windows/

# Option 2: winget
winget install Python.Python.3.12
```

After install, verify one of these works:
```powershell
py -3 --version
python --version
python3 --version
```

The Windows wrapper scripts automatically try `py -3`, then `python3`, then `python`.

### Installing FFmpeg

**Windows:**
```powershell
# Using winget
winget install Gyan.FFmpeg

# Or download from https://www.gyan.dev/ffmpeg/builds/
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Linux (Arch):**
```bash
sudo pacman -S ffmpeg
```

## Usage

### Basic Usage

Process supported video files in the current directory:

```bash
# Linux/macOS - H.264 encoding
./unix/video/h264-transcode.sh      # MP4 input
./unix/video/h264-avi-transcode.sh  # AVI input
./unix/video/h264-mov-transcode.sh  # MOV input
./unix/video/h264-m4v-transcode.sh  # M4V input
./unix/video/h264-mpg-transcode.sh   # MPG input
./unix/video/h264-mpeg-transcode.sh  # MPEG input/output
./unix/video/h264-flv-transcode.sh  # FLV input
./unix/video/h264-wmv-transcode.sh  # WMV input
./unix/video/transcode_all_video.sh        # AVI, FLV, MOV, M4V, MPG, MPEG, WMV, then MP4 inputs

# Linux/macOS - HEVC encoding
./unix/video/hevc-transcode.sh

# Windows - H.264 encoding (PowerShell)
.\windows\video\h264-transcode.ps1      # MP4 input
.\windows\video\h264-avi-transcode.ps1  # AVI input
.\windows\video\h264-mov-transcode.ps1  # MOV input
.\windows\video\h264-m4v-transcode.ps1  # M4V input
.\windows\video\h264-mpg-transcode.ps1   # MPG input
.\windows\video\h264-mpeg-transcode.ps1  # MPEG input/output
.\windows\video\h264-flv-transcode.ps1  # FLV input
.\windows\video\h264-wmv-transcode.ps1  # WMV input
.\windows\video\transcode_all_video.ps1        # AVI, FLV, MOV, M4V, MPG, MPEG, WMV, then MP4 inputs

# Windows - HEVC encoding (PowerShell)
.\windows\video\hevc-transcode.ps1

# Linux/macOS - HEVC encoding (MKV input/output)
./unix/video/hevc-mkv-transcode.sh
./unix/video/hevc-mkv-transcode.sh -t 8

# Windows - HEVC encoding (MKV input/output)
.\windows\video\hevc-mkv-transcode.ps1
.\windows\video\hevc-mkv-transcode.ps1 -Threads 8

# Cross-platform Python - HEVC encoding (MKV input/output)
python3 ./cross-platform/hevc-mkv-transcode.py
python3 ./cross-platform/hevc-mkv-transcode.py --threads 8

# Cross-platform Python - File type tools
python3 ./cross-platform/file-type-report.py /path/to/media
python3 ./cross-platform/files-by-extension.py /path/to/media mp4
python3 ./cross-platform/recursive-file-type-report.py /path/to/media
python3 ./cross-platform/recursive-file-type-report.py --detailed /path/to/media
python3 ./cross-platform/one-level-recursive-file-type-report.py
python3 ./cross-platform/one-level-recursive-file-type-report.py --output /path/to/report.txt

# Linux/macOS - Audio conversion to 256k MP3
./unix/audio/flac-to-mp3.sh
./unix/audio/wav-to-mp3.sh
./unix/audio/transcode_all_audio.sh
# Optional audio wrapper flags: -r/--recurse, -t/--threads, --quality, --config, --skip-dir
# Hardware encoder flags (-q, -n, -a) are video-only and do not accelerate MP3 conversion.

# Windows - Audio conversion to 256k MP3
.\windows\audio\flac-to-mp3.ps1
.\windows\audio\wav-to-mp3.ps1
.\windows\audio\transcode_all_audio.ps1
```

### Recursive Processing

Process supported video files from the current directory downward:

```bash
# Linux/macOS
./unix/video/h264-transcode.sh -r
./unix/video/h264-avi-transcode.sh -r
./unix/video/h264-mov-transcode.sh -r
./unix/video/h264-m4v-transcode.sh -r
./unix/video/h264-mpg-transcode.sh -r
./unix/video/h264-mpeg-transcode.sh -r
./unix/video/h264-flv-transcode.sh -r
./unix/video/h264-wmv-transcode.sh -r
./unix/video/transcode_all_video.sh -r
./unix/video/hevc-transcode.sh -r
./unix/video/hevc-mkv-transcode.sh -r
./unix/video/hevc-mkv-transcode.sh -r -t 8
./unix/audio/flac-to-mp3.sh -r
./unix/audio/wav-to-mp3.sh -r
./unix/audio/transcode_all_audio.sh -r

# Windows
.\windows\video\h264-transcode.ps1 -Recurse
.\windows\video\h264-avi-transcode.ps1 -Recurse
.\windows\video\h264-mov-transcode.ps1 -Recurse
.\windows\video\h264-m4v-transcode.ps1 -Recurse
.\windows\video\h264-mpg-transcode.ps1 -Recurse
.\windows\video\h264-mpeg-transcode.ps1 -Recurse
.\windows\video\h264-flv-transcode.ps1 -Recurse
.\windows\video\h264-wmv-transcode.ps1 -Recurse
.\windows\video\transcode_all_video.ps1 -Recurse
.\windows\video\hevc-transcode.ps1 -Recurse
.\windows\video\hevc-mkv-transcode.ps1 -Recurse
.\windows\video\hevc-mkv-transcode.ps1 -Recurse -Threads 8
.\windows\audio\flac-to-mp3.ps1 -Recurse
.\windows\audio\wav-to-mp3.ps1 -Recurse
.\windows\audio\transcode_all_audio.ps1 -Recurse
python3 ./cross-platform/hevc-mkv-transcode.py --recurse
python3 ./cross-platform/hevc-mkv-transcode.py --recurse --threads 8
python3 ./cross-platform/file-type-report.py --recursive /path/to/media
python3 ./cross-platform/files-by-extension.py --recursive /path/to/media .mp4
python3 ./cross-platform/recursive-file-type-report.py --detailed /path/to/media
```

> Note: Transcoding wrappers now standardize on `-r` / `--recurse` for recursive operation.  
> The standalone file-report helpers still use `--recursive`.

### Hardware Acceleration

Use hardware encoders for significantly faster video processing (2-10x speedup). These flags are video-only; MP3 audio conversion uses the MP3 encoder and is not accelerated by `-q`, `-n`, or `-a`.

| Flag | Encoder | Platform |
|------|---------|----------|
| `-q` / `-UseQuickSync` | Intel Quick Sync | Intel 4th gen+ |
| `-n` / `-UseNVENC` | NVIDIA NVENC | GTX 600+ / RTX |
| `-a` / `-UseAMF` | AMD AMF | RX 400+ / Vega |

**Examples:**

```bash
# Linux/macOS with Intel Quick Sync
./unix/video/h264-transcode.sh -r -q
./unix/video/h264-avi-transcode.sh -r -q
./unix/video/h264-mov-transcode.sh -r -q
./unix/video/h264-m4v-transcode.sh -r -q
./unix/video/h264-mpg-transcode.sh -r -q
./unix/video/h264-mpeg-transcode.sh -r -q
./unix/video/h264-flv-transcode.sh -r -q
./unix/video/h264-wmv-transcode.sh -r -q
./unix/video/hevc-transcode.sh -q
./unix/video/hevc-mkv-transcode.sh -q

# Linux/macOS with NVIDIA GPU
./unix/video/h264-transcode.sh -r -n
./unix/video/h264-avi-transcode.sh -r -n
./unix/video/h264-mov-transcode.sh -r -n
./unix/video/h264-m4v-transcode.sh -r -n
./unix/video/h264-mpg-transcode.sh -r -n
./unix/video/h264-mpeg-transcode.sh -r -n
./unix/video/h264-flv-transcode.sh -r -n
./unix/video/h264-wmv-transcode.sh -r -n
./unix/video/hevc-transcode.sh -n

# Windows with NVIDIA GPU
.\windows\video\h264-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-avi-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-mov-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-m4v-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-mpg-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-mpeg-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-flv-transcode.ps1 -Recurse -UseNVENC
.\windows\video\h264-wmv-transcode.ps1 -Recurse -UseNVENC
.\windows\video\hevc-transcode.ps1 -UseNVENC
.\windows\video\hevc-mkv-transcode.ps1 -UseNVENC
python3 .\cross-platform\hevc-mkv-transcode.py --nvenc
```

See [HARDWARE_ACCEL_GUIDE.md](HARDWARE_ACCEL_GUIDE.md) for detailed setup instructions.

### Quality, Config, and Skip-Directory Options

The `transcode_cli.py`-backed wrappers support runtime overrides and user config:

- `--quality <N>` (Unix wrappers) / `-Quality <N>` (PowerShell wrappers): override video quality for this invocation (`0..51`).
- `--skip-dir <PATH>` (Unix wrappers) / `-SkipDir <PATH[,PATH2...]>` (PowerShell wrappers): skip processing files under the provided directory path prefix.
- `--config <PATH>` (Unix wrappers) / `-ConfigPath <PATH>` (PowerShell wrappers): read user preferences from a JSON config file.

Config precedence is: CLI arguments > config values > profile defaults.

Default config path:
- Linux/macOS: `${XDG_CONFIG_HOME:-~/.config}/ffmpeg-utility-scripts/config.json`
- Windows: `%APPDATA%\ffmpeg-utility-scripts\config.json`

Example config:

```json
{
  "skip_dirs": [
    "/mnt/c/0-ready",
    "/mnt/c/archive"
  ],
  "quality": {
    "default_video": 26,
    "h264_wmv": 24,
    "hevc_mp4": 25
  }
}
```

Invalid config quality values now fail gracefully with an `Error: ...` message (same `0..51` validation as CLI quality).



## How It Works

1. **File Preparation**: If a selected input filename contains spaces, that file is renamed to use underscores immediately before encoding/conversion
2. **File Collection**: Scans for eligible `.mp4`, `.avi`, `.mov`, `.m4v`, `.mkv`, `.flac`, or `.wav` files depending on the script (skips already-transcoded or already-converted files), scans all regular files when generating file type reports, combines detailed recursive reports for direct child folders, or lists full paths for a requested extension
3. **UHD/4K Detection**: Detects if input video is larger than 1080p and applies aspect-safe downscaling where supported
4. **Transcoding/Conversion**: Converts video using specified codec, copies audio for video workflows (and MKV subtitles in the MKV workflow), or converts FLAC/WAV audio to 256k MP3
5. **Verification**: Validates output file integrity with ffprobe
6. **Cleanup**: Deletes source file only after successful verification

## Output Files

- **H.264 (MP4/AVI/MOV workflows)**: Creates `*_REDU.mp4` files
- **H.264 (M4V workflow)**: Creates `*_REDU.m4v` files
- **HEVC (MP4 workflow)**: Creates `*_HEVC.mp4` files
- **HEVC (MKV workflow)**: Creates `*_HEVC.mkv` files
- **Audio conversion**: Creates `*.mp3` files at 256 kbps for FLAC/WAV inputs
- **Temporary**: Uses `*.tmp.mp4`, `*.tmp.mkv`, or `*.tmp.mp3` during processing (auto-cleaned)

## Safety Features

- ✓ Output file is verified with ffprobe before source deletion
- ✓ Active temporary output is cleaned up on interruption (Ctrl+C / SIGTERM)
- ✓ Skips files that already have processed versions
- ✓ Handles filenames with spaces safely
- ✓ Validates file paths to prevent injection attacks

## Encoding Settings

| Setting | Software | Intel QSV | NVIDIA NVENC | AMD AMF |
|---------|----------|-----------|--------------|---------|
| Quality (default) | CRF 26 | Global Quality 26 | CQ 26 | QP 26 |
| H.264 Preset | veryfast | fast | p4 | speed |
| HEVC Preset | medium | medium | p4 | speed |

**Note:** Hardware encoders trade some quality for speed. For archival storage, software encoding is recommended.
For MKV HEVC scripts, thread limits are available as `-t <N>` (Unix), `-Threads <N>` (PowerShell), and `--threads <N>` (Python), with `libx265` using that value for its worker pool.
WMV-specific H.264 scripts (`h264-wmv-transcode.sh` and `h264-wmv-transcode.ps1`) use quality level **24** across software and hardware encoder paths per the WMV requirement.

## Exit Codes

For `cross-platform/transcode_cli.py` and `cross-platform/hevc-mkv-transcode.py`:

- `0`: No hard failures. This includes runs where transcoding succeeded but source cleanup (rename/delete) had warning-level issues; outputs are kept and a cleanup warning summary is printed.
- `1`: One or more hard failures (transcode, verification, move/finalize, interruption, invalid arguments, or config errors).

Optional strict mode:

- `--strict-cleanup`: upgrades cleanup warnings to hard failures, causing exit code `1` when cleanup issues occur.

## Troubleshooting

### "No eligible MP4/AVI/MOV/M4V files found to process"
- The selected script found no matching input files that have not already been processed
- Check that your files use the extension for the script you ran: `.mp4`, `.avi`, `.mov`, `.m4v`, `.mpg`, `.mpeg`, `.flv`, `.wmv`, `.mkv`, `.flac`, or `.wav`
- Check that you don't already have `*_REDU.mp4`, `*_HEVC.mp4`, or `*_HEVC.mkv` versions

### "ffmpeg failed" or "Output file verification failed"
- Ensure FFmpeg is installed and in your PATH: `ffmpeg -version`
- Check that the source file isn't corrupted: `ffprobe -v error input.mp4`
- For hardware encoding, ensure your GPU/drivers support the codec
- For very large H.264 sources (for example, 4K/UHD inputs), use the latest scripts so automatic 1080p fallback can trigger correctly and avoid high-memory encoder failures

### Hardware encoding not available
- Check supported encoders: `ffmpeg -encoders | grep -E "(qsv|nvenc|amf)"`
- Update your GPU drivers
- Some FFmpeg builds don't include hardware encoders

## Performance Comparison

Approximate encoding speeds (relative to software encoding):

| Method | Speed | Quality | Power Usage |
|--------|-------|---------|-------------|
| Software (CPU) | 1x (baseline) | Best | High |
| Intel Quick Sync | 2-5x | Good | Low |
| NVIDIA NVENC | 3-10x | Good | Medium |
| AMD AMF | 2-5x | Good | Medium |

## License

These scripts are provided as-is for personal and commercial use. No warranty is provided.

## Contributing

Feel free to submit issues or pull requests for bug fixes and improvements.
