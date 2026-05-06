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
- **Smart file handling**: Auto-renames files with spaces, skips already-processed files
- **File type reporting**: Counts files by extension, lists matching full file paths, and generates per-folder reports

## Repository Structure

```
.
├── cross-platform/
│   ├── file-type-report.py        # Count files by file type (Python, cross-platform)
│   ├── files-by-extension.py      # List full paths matching an extension (Python, cross-platform)
│   ├── recursive-file-type-report.py # Per-folder type reports (Python, cross-platform)
│   └── hevc-mkv-transcode.py      # HEVC/H.265 encoding for MKV (Python, cross-platform)
├── unix/
│   ├── flac-to-mp3.sh             # FLAC to 256k MP3 (Bash)
│   ├── h264-transcode.sh          # H.264 encoding for MP4 (Bash)
│   ├── h264-avi-transcode.sh      # H.264 encoding for AVI (Bash)
│   ├── h264-mov-transcode.sh      # H.264 encoding for MOV (Bash)
│   ├── hevc-transcode.sh          # HEVC/H.265 encoding for MP4 (Bash)
│   ├── hevc-mkv-transcode.sh      # HEVC/H.265 encoding for MKV (Bash)
│   └── wav-to-mp3.sh              # WAV to 256k MP3 (Bash)
├── windows/
│   ├── flac-to-mp3.ps1            # FLAC to 256k MP3 (PowerShell)
│   ├── h264-transcode.ps1         # H.264 encoding for MP4 (PowerShell)
│   ├── h264-avi-transcode.ps1     # H.264 encoding for AVI (PowerShell)
│   ├── h264-mov-transcode.ps1     # H.264 encoding for MOV (PowerShell)
│   ├── hevc-transcode.ps1         # HEVC/H.265 encoding for MP4 (PowerShell)
│   ├── hevc-mkv-transcode.ps1     # HEVC/H.265 encoding for MKV (PowerShell)
│   └── wav-to-mp3.ps1             # WAV to 256k MP3 (PowerShell)
├── HARDWARE_ACCEL_GUIDE.md        # Hardware acceleration setup guide
└── README.md                      # This file
```

## Requirements

- **FFmpeg** 4.0 or later (must be in PATH)
- **Bash** 4.0+ (for Unix scripts)
- **PowerShell** 5.1+ (for Windows scripts)
- **ffprobe** (for output verification)
- **Python** 3.9+ (for cross-platform Python scripts)

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
./unix/h264-transcode.sh      # MP4 input
./unix/h264-avi-transcode.sh  # AVI input
./unix/h264-mov-transcode.sh  # MOV input

# Linux/macOS - HEVC encoding
./unix/hevc-transcode.sh

# Windows - H.264 encoding (PowerShell)
.\windows\h264-transcode.ps1      # MP4 input
.\windows\h264-avi-transcode.ps1  # AVI input
.\windows\h264-mov-transcode.ps1  # MOV input

# Windows - HEVC encoding (PowerShell)
.\windows\hevc-transcode.ps1

# Linux/macOS - HEVC encoding (MKV input/output)
./unix/hevc-mkv-transcode.sh
./unix/hevc-mkv-transcode.sh -t 8

# Windows - HEVC encoding (MKV input/output)
.\windows\hevc-mkv-transcode.ps1
.\windows\hevc-mkv-transcode.ps1 -Threads 8

# Cross-platform Python - HEVC encoding (MKV input/output)
python3 ./cross-platform/hevc-mkv-transcode.py
python3 ./cross-platform/hevc-mkv-transcode.py --threads 8

# Cross-platform Python - File type tools
python3 ./cross-platform/file-type-report.py /path/to/media
python3 ./cross-platform/files-by-extension.py /path/to/media mp4
python3 ./cross-platform/recursive-file-type-report.py /path/to/media

# Linux/macOS - Audio conversion to 256k MP3
./unix/flac-to-mp3.sh
./unix/wav-to-mp3.sh

# Windows - Audio conversion to 256k MP3
.\windows\flac-to-mp3.ps1
.\windows\wav-to-mp3.ps1
```

### Recursive Processing

Process supported video files from the current directory downward:

```bash
# Linux/macOS
./unix/h264-transcode.sh -r
./unix/h264-avi-transcode.sh -r
./unix/h264-mov-transcode.sh -r
./unix/hevc-transcode.sh -r
./unix/hevc-mkv-transcode.sh -r
./unix/hevc-mkv-transcode.sh -r -t 8
./unix/flac-to-mp3.sh -r
./unix/wav-to-mp3.sh -r

# Windows
.\windows\h264-transcode.ps1 -Recurse
.\windows\h264-avi-transcode.ps1 -Recurse
.\windows\h264-mov-transcode.ps1 -Recurse
.\windows\hevc-transcode.ps1 -Recurse
.\windows\hevc-mkv-transcode.ps1 -Recurse
.\windows\hevc-mkv-transcode.ps1 -Recurse -Threads 8
.\windows\flac-to-mp3.ps1 -Recurse
.\windows\wav-to-mp3.ps1 -Recurse
python3 ./cross-platform/hevc-mkv-transcode.py --recurse
python3 ./cross-platform/hevc-mkv-transcode.py --recurse --threads 8
python3 ./cross-platform/file-type-report.py --recursive /path/to/media
python3 ./cross-platform/files-by-extension.py --recursive /path/to/media .mp4
```

### Hardware Acceleration

Use hardware encoders for significantly faster processing (2-10x speedup):

| Flag | Encoder | Platform |
|------|---------|----------|
| `-q` / `-UseQuickSync` | Intel Quick Sync | Intel 4th gen+ |
| `-n` / `-UseNVENC` | NVIDIA NVENC | GTX 600+ / RTX |
| `-a` / `-UseAMF` | AMD AMF | RX 400+ / Vega |

**Examples:**

```bash
# Linux/macOS with Intel Quick Sync
./unix/h264-transcode.sh -r -q
./unix/h264-avi-transcode.sh -r -q
./unix/h264-mov-transcode.sh -r -q
./unix/hevc-transcode.sh -q
./unix/hevc-mkv-transcode.sh -q

# Linux/macOS with NVIDIA GPU
./unix/h264-transcode.sh -r -n
./unix/h264-avi-transcode.sh -r -n
./unix/h264-mov-transcode.sh -r -n
./unix/hevc-transcode.sh -n

# Windows with NVIDIA GPU
.\windows\h264-transcode.ps1 -Recurse -UseNVENC
.\windows\h264-avi-transcode.ps1 -Recurse -UseNVENC
.\windows\h264-mov-transcode.ps1 -Recurse -UseNVENC
.\windows\hevc-transcode.ps1 -UseNVENC
.\windows\hevc-mkv-transcode.ps1 -UseNVENC
python3 .\cross-platform\hevc-mkv-transcode.py --nvenc
```

See [HARDWARE_ACCEL_GUIDE.md](HARDWARE_ACCEL_GUIDE.md) for detailed setup instructions.

## How It Works

1. **File Preparation**: Renames files with spaces to use underscores
2. **File Collection**: Scans for eligible `.mp4`, `.avi`, `.mov`, `.mkv`, `.flac`, or `.wav` files depending on the script (skips already-transcoded or already-converted files), scans all regular files when generating file type reports, or lists full paths for a requested extension
3. **UHD/4K Detection**: Detects if input video is larger than 1080p and applies aspect-safe downscaling where supported
4. **Transcoding/Conversion**: Converts video using specified codec, copies audio for video workflows (and MKV subtitles in the MKV workflow), or converts FLAC/WAV audio to 256k MP3
5. **Verification**: Validates output file integrity with ffprobe
6. **Cleanup**: Deletes source file only after successful verification

## Output Files

- **H.264 (MP4/AVI/MOV workflows)**: Creates `*_REDU.mp4` files
- **HEVC (MP4 workflow)**: Creates `*_HEVC.mp4` files
- **HEVC (MKV workflow)**: Creates `*_HEVC.mkv` files
- **Audio conversion**: Creates `*.mp3` files at 256 kbps for FLAC/WAV inputs
- **Temporary**: Uses `*.tmp.mp4`, `*.tmp.mkv`, or `*.tmp.mp3` during processing (auto-cleaned)

## Safety Features

- ✓ Output file is verified with ffprobe before source deletion
- ✓ Temporary files are cleaned up on interruption (Ctrl+C)
- ✓ Skips files that already have processed versions
- ✓ Handles filenames with spaces safely
- ✓ Validates file paths to prevent injection attacks

## Encoding Settings

| Setting | Software | Intel QSV | NVIDIA NVENC | AMD AMF |
|---------|----------|-----------|--------------|---------|
| Quality | CRF 24 | Global Quality 24 | CQ 24 | QP 24 |
| H.264 Preset | veryfast | fast | p4 | speed |
| HEVC Preset | medium | medium | p4 | speed |

**Note:** Hardware encoders trade some quality for speed. For archival storage, software encoding is recommended.
For MKV HEVC scripts, thread limits are available as `-t <N>` (Unix), `-Threads <N>` (PowerShell), and `--threads <N>` (Python), with `libx265` using that value for its worker pool.

## Troubleshooting

### "No eligible MP4/AVI/MOV files found to process"
- The selected script found no matching input files that have not already been processed
- Check that your files use the extension for the script you ran: `.mp4`, `.avi`, or `.mov`
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
